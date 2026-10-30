# Recovering a Neo Ghost from error 07 / error 05

## What happened to mine

1. The Neo worked, but the official update site was dead. I plugged it into Linux, which **mounted it read-write**, and read every file. Then the device dropped off the USB bus while still mounted.
   - Linux left the "dirty" flag set: bit 0 of boot-sector byte `0x25`, so `0xDC` became `0xDD`.
   - The FAT ended up damaged.
   - → **Error 07** at power-on.
2. First restore attempt: a full backup image written back. The check said "100% OK", but that was **wrong**: it was reading Linux's page cache, not the flash. The image also still had `0xDD`. → **Error 05 "Contact support"**.
3. Other mistakes made along the way, so you can avoid them:
   - writing to the **whole disk** (`/dev/sdb`) instead of the **partition** (`/dev/sdb1`, which starts 18 KiB in);
   - comparing the wrong offsets;
   - believing "the Neo erases itself".
4. At some point, on error 05, a button press let the Neo continue, and **it reformatted its own partition**: empty FAT, empty root, data blocks erased to `0xFF`, boot sector rewritten from its own template. That the button press caused it is a *strong hypothesis*.
5. **What fixed it:**
   - Write my backup image to the **partition only**, with `0x25` set back to `0xDC`.
   - Write the first 64 KiB (boot + FAT + root) **one 2048-byte sector at a time** with `O_DIRECT|O_SYNC`. A single big write there didn't stick.
   - Verify the whole partition with `O_DIRECT` reads: **0 differences**, `fsck.vfat -n`: 624 files.
6. The Neo booted with **no error code**. Read back after boot: the Neo had written nothing to its system area.

## Procedure

```bash
# 0. Never let the desktop mount it:
gsettings set org.gnome.desktop.media-handling automount false
gsettings set org.gnome.desktop.media-handling automount-open false
# 1. Find the PARTITION (the Neo is a ~125M disk with one partition):
lsblk -o NAME,SIZE,VENDOR,MODEL
# 2. Restore YOUR backup (fixes byte 0x25, sector-by-sector system area, full O_DIRECT check, fsck, eject):
sudo python3 tools/neo_restore.py --dev /dev/sdX1 neo_backup.img
```

If the result shows mismatching blocks, run it again. Then unplug the Neo and power it on.

## If you have no backup

The file system area alone (boot sector, FAT and root directory, the first 7 sectors) can be rebuilt from the file list. But **the course data itself can't be recreated** if the Neo erased it, and this repo does not distribute the iGolf database. If your data area is still intact (check whether `idx/`, `name/` and `000/` contents are still there with a raw read), open an issue: rebuilding a FAT for intact data is possible.

## Lessons

- Never mount the Neo read-write, and turn off automount before plugging it in.
- Always target `/dev/sdX1`. Check that its size is 131,086,336 bytes before writing.
- Verify with `O_DIRECT` reads, and re-check about 30 s after writing.
- Write the system area sector by sector.
- Never write back an image that `fsck -a` has "repaired": it rewrites the Neo's non-standard boot fields.
- On error 05: don't press anything, switch the Neo off.

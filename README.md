# Bushnell Neo Ghost: recovery and custom courses

The official Bushnell / iGolf update service for the **Neo Ghost** golf GPS is gone. This repo documents its storage and course database, as reverse-engineered from one unit. It also provides Python tools to:

- **back up** the device and **recover** it from **error 07 / error 05 "Contact support"** (corrupted file system);
- **read** the built-in iGolf database (29,544 courses, data from December 2014);
- **add a missing course**: hole positions and pars go into an existing slot of the database.

Status (tested on one Neo Ghost, ref. 368221):

- **Recovery from error 07 / 05:** worked.
- **Edited course:** shown by the Neo with its new name, at its new location, and it opens.
- **On-course test:** pending.

> ⚠️ Use at your own risk. Everything here was written to be safe (copy-first, verify-after), but it comes with no warranty. **This repo does not contain the iGolf database, the firmware or any disk image.** You need your own backup.

## 1. Before anything else: back up your Neo

```bash
# turn off desktop automount first (GNOME):
gsettings set org.gnome.desktop.media-handling automount false
lsblk                                   # the Neo is a ~125M disk, USB 04d8:0009 "Microchip Mass Storage"
sudo python3 tools/neo_backup.py --dev /dev/sdX1 neo_backup.img     # sdX1 = the PARTITION
```

Rules learned the hard way:

- **Never keep the Neo mounted read-write**, on Linux especially. Mine got corrupted (error 07) because the volume stayed mounted read-write while the device dropped off the USB bus and came back.
- On **error 05**, **don't press anything to continue**. Switch the Neo off. On my unit, the file system area ended up reformatted.
- Always work on the **partition** (`/dev/sdX1`). An image of the partition must never be written to the whole disk (`/dev/sdX`).

## 2. Recover from error 07 / 05

You need an image of **your own** unit taken while it was healthy.

```bash
sudo python3 tools/neo_restore.py --dev /dev/sdX1 neo_backup.img
```

The script:

- resets the "dirty" byte (`0x25` = `0xDC`);
- writes the system area one 2048-byte sector at a time;
- checks the whole partition with direct reads;
- runs `fsck`;
- ejects the device.

Details and the full story are in [docs/RECOVERY.md](docs/RECOVERY.md).

## 3. Read the database

```bash
sudo mkdir -p neo_mount && sudo mount -o ro,loop neo_backup.img neo_mount
export NEO_ROOT=$PWD/neo_mount
python3 tools/neodb.py selftest
python3 tools/neodb.py near 43.8318 4.6011 5      # closest courses to a GPS point
python3 tools/neodb.py dump 023 648               # one course: name, holes, pars
```

## 4. Add a missing course

Short version (full guide: [docs/ADD_A_COURSE.md](docs/ADD_A_COURSE.md)):

1. **Describe the course** in JSON: for each hole, give the green front/center/back, 1 to 3 tees and the par. See [examples/st_roman_beaucaire.json](examples/st_roman_beaucaire.json).
2. **Pick a slot to sacrifice** with `neodb.py near`: a course you'll never play, inside an index file, whose neighbours in longitude surround your course.
3. **Forge it on a copy:**
   `sudo python3 tools/forge_course.py neo_backup.img new.img IDX SLOT "My Course" course.json LAT LON`
   It prints the 2048-byte sectors that changed (usually 4).
4. **Write only those sectors:**
   `sudo python3 tools/write_sectors.py --dev /dev/sdX1 neo_backup.img new.img s1,s2,s3,s4`
   It checks the device state first, writes, re-checks after 30 s and ejects. `new.img` becomes your new reference image.

The Neo only lists courses within roughly 15 km. To test at home, forge a temporary **shifted copy** (`forge_course.py ... LAT LON dLAT dLON`) into a slot near your own longitude, then restore that slot.

## 5. Format summary

| Item | Format |
|---|---|
| Disk | 2048-byte sectors; one partition at byte 18432, 131,086,336 bytes; custom FAT12, OEM name `L1 NEO`; boot byte `0x25` = `0xDC` when clean |
| `idx/NNN` (29 files × 1024 entries) | 32-byte **plain-text** entries **sorted by longitude**: lat, lon (int32 × 1e7), record offset, key value `ck` (u16), pointers to the data and name files |
| `000/`–`004/` | 1808-byte course records, XOR with a 33-byte key rotated by `ck` |
| Record | center; copy of `ck`; **displayed name**; 18 hole blocks (green F/C/B, 4 custom points + their hazard codes, 3 tees); hole count; pars |
| `name/` | 50-byte names, XOR with a per-`ck%33` keystream. The Neo does **not** display this copy |
| `idx/ghost.idx` | header plus a min/max longitude table per index file. The last 116 bytes are still unknown, but they are **not checked** against the edits described here |

Full spec: [docs/FORMAT.md](docs/FORMAT.md). Keys: [tools/keys.json](tools/keys.json).

## Open questions / help wanted

- Hazard codes are **partly decoded**: side, greenside or fairway, bunker or water ([docs/FORMAT.md §5.1](docs/FORMAT.md)). Still missing: the `E` type, the 4th byte, and how the Neo displays each code.
- What `ghost.idx`'s first u32 (`0xEBEAEA58`) and its last 116 bytes are.
- The `FW.bin` firmware (probably PIC24/dsPIC) has not been disassembled.
- Is the format the same on the **Neo XS / Neo Ion / Neo+**? Reports welcome (open an issue).

## Credits

Reverse-engineering by the repo owner with an AI agent (Hermes) running on a Raspberry Pi 5, October 2026. A French write-up of the whole investigation is in [docs/RAPPORT_FR.md](docs/RAPPORT_FR.md).

The iGolf course data and the Bushnell firmware belong to their owners and are **not** distributed here. This project documents a file format for interoperability, so owners can keep using their own device.

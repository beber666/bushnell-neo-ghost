#!/usr/bin/env python3
"""neo_restore.py - write a full partition image back to the Neo (fix for error 07 / 05).

    sudo python3 neo_restore.py --dev /dev/sdX1 neo_backup.img

Use YOUR OWN backup image of a healthy unit (see neo_backup.py).
- Refuses if the partition is mounted or if its size differs from the image.
- Sets boot-sector byte 0x25 to 0xDC (Linux leaves 0xDD = "dirty" after a read-write mount).
- Compare-then-write. The system area (first 64 KiB: boot sector, FAT, root dir) is written ONE
  2048-byte sector at a time - bigger writes there were silently dropped by the device.
- Waits 30 s, then verifies the WHOLE partition with O_DIRECT reads (not the page cache),
  runs fsck.vfat -n and powers the device off.
"""
import argparse, os, sys, time, mmap, subprocess

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--dev", required=True, help="the PARTITION, e.g. /dev/sdb1 (never the whole disk)")
ap.add_argument("image")
ap.add_argument("--no-eject", action="store_true")
a = ap.parse_args()
S, SYS, CH = 2048, 64 * 1024, 64 * 1024

img = bytearray(open(a.image, "rb").read())
if img[0x25] == 0xDD: img[0x25] = 0xDC
img = bytes(img)
if a.dev in open("/proc/mounts").read(): sys.exit(f"ABORT: {a.dev} is mounted")
fd = os.open(a.dev, os.O_RDWR | os.O_DIRECT | os.O_SYNC)
size = os.lseek(fd, 0, os.SEEK_END)
if size != len(img): sys.exit(f"ABORT: device size {size} != image size {len(img)} (whole disk instead of partition?)")
big = mmap.mmap(-1, CH); one = mmap.mmap(-1, S)
written = 0; t0 = time.time()
for off in range(0, SYS, S):                       # system area: sector by sector
    os.preadv(fd, [one], off)
    if bytes(one) != img[off:off + S]:
        one.seek(0); one.write(img[off:off + S]); os.pwritev(fd, [one], off); written += 1
for off in range(SYS, size, CH):                   # data area: 64 KiB chunks
    n = min(CH, size - off); v = memoryview(big)[:n]
    os.preadv(fd, [v], off)
    if bytes(v) != img[off:off + n]:
        big.seek(0); big.write(img[off:off + n]); os.pwritev(fd, [memoryview(big)[:n]], off); written += n // S
    if off % (16 << 20) == 0: print(f"  {off >> 20}/{size >> 20} MiB", flush=True)
os.close(fd)
print(f"{written} sectors rewritten in {(time.time() - t0) / 60:.1f} min; waiting 30 s...", flush=True)
time.sleep(30)
fd = os.open(a.dev, os.O_RDONLY | os.O_DIRECT); bad = []
for off in range(0, size, CH):
    n = min(CH, size - off); v = memoryview(big)[:n]; os.preadv(fd, [v], off)
    if bytes(v) != img[off:off + n]: bad.append(off // S)
os.close(fd)
subprocess.run(["blockdev", "--flushbufs", a.dev])
fsck = subprocess.run(["fsck.vfat", "-n", a.dev], capture_output=True, text=True).stdout.strip().splitlines()
print("mismatching 64 KiB blocks (first sector):", bad[:20], "| fsck:", fsck[-1] if fsck else "?")
if bad: print("Re-run the script: the system area sometimes needs a second pass.")
if not a.no_eject:
    ej = subprocess.run(["udisksctl", "power-off", "-b", a.dev.rstrip("0123456789")], capture_output=True, text=True)
    print("eject:", "OK" if ej.returncode == 0 else ej.stderr.strip())
print("RESULT:", "SUCCESS" if not bad else "FAILURE")
sys.exit(0 if not bad else 1)

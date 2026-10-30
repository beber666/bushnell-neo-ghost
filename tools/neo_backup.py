#!/usr/bin/env python3
"""neo_backup.py - make a full image of the Neo partition (do this FIRST, while it still works).

    sudo python3 neo_backup.py --dev /dev/sdX1 neo_backup.img

- Reads with O_DIRECT (real device content, not the cache), never writes to the device.
- Refuses if the partition is mounted read-write.
- Reads twice and compares, then prints the SHA-256.
Find the partition with `lsblk`: the Neo Ghost shows up as a ~125M disk (USB 04d8:0009
"Microchip Mass Storage Drive") with one partition. Use the PARTITION (sdX1), not the disk (sdX).
"""
import argparse, hashlib, mmap, os, sys

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--dev", required=True); ap.add_argument("out")
a = ap.parse_args()
for line in open("/proc/mounts"):
    p = line.split()
    if p[0] == a.dev and "rw" in p[3].split(","): sys.exit(f"ABORT: {a.dev} is mounted read-write - unmount it")
CH = 64 * 1024

def read_all():
    fd = os.open(a.dev, os.O_RDONLY | os.O_DIRECT); size = os.lseek(fd, 0, os.SEEK_END)
    buf = mmap.mmap(-1, CH); out = bytearray()
    for off in range(0, size, CH):
        n = min(CH, size - off); v = memoryview(buf)[:n]; os.preadv(fd, [v], off); out += v
    os.close(fd); return bytes(out)

d1 = read_all(); d2 = read_all()
if d1 != d2: sys.exit("ABORT: two reads differ - unstable device/cable, try again")
open(a.out, "wb").write(d1)
print(f"{a.out}: {len(d1)} bytes, sha256 {hashlib.sha256(d1).hexdigest()}")
print("Boot sector OEM name:", d1[3:11], "| dirty byte 0x25 =", hex(d1[0x25]), "(0xDC = clean)")

#!/usr/bin/env python3
"""write_sectors.py - write a few 2048-byte sectors of an image to the Neo, safely.

    sudo python3 write_sectors.py --dev /dev/sdX1 EXPECTED.img TARGET.img s1,s2,... [--wait SECONDS]

- EXPECTED.img = what the Neo contains now; TARGET.img = what it should contain.
- Refuses to run if the partition is mounted, if its size differs from the images,
  or if any sector on the device matches neither EXPECTED nor TARGET (nothing is written then).
- Writes one sector at a time with O_DIRECT|O_SYNC, waits 30 s (the controller commits late),
  re-reads with O_DIRECT, runs fsck.vfat -n, then powers the device off (udisksctl).
- --wait: wait up to N seconds for the device to appear (plug the Neo in USB mode).
"""
import argparse, os, sys, time, mmap, subprocess

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--dev", required=True, help="the PARTITION, e.g. /dev/sdb1 (never the whole disk)")
ap.add_argument("expected"); ap.add_argument("target"); ap.add_argument("sectors")
ap.add_argument("--wait", type=int, default=0)
ap.add_argument("--no-eject", action="store_true")
a = ap.parse_args()
S = 2048
exp = open(a.expected, "rb").read(); tgt = open(a.target, "rb").read()
secs = [int(x) for x in a.sectors.split(",") if x]
assert len(exp) == len(tgt)

t0 = time.time()
while not os.path.exists(a.dev):
    if time.time() - t0 > a.wait: sys.exit(f"{a.dev} not found")
    time.sleep(3)
time.sleep(3)
if a.dev in open("/proc/mounts").read(): sys.exit(f"ABORT: {a.dev} is mounted - unmount it first")
fd = os.open(a.dev, os.O_RDONLY | os.O_DIRECT)
size = os.lseek(fd, 0, os.SEEK_END)
if size != len(exp): sys.exit(f"ABORT: device size {size} != image size {len(exp)} (whole disk instead of partition?)")
buf = mmap.mmap(-1, S)
def rd(fd, s): os.preadv(fd, [buf], s * S); return bytes(buf)
state = {}
for s in secs:
    cur = rd(fd, s)
    state[s] = "expected" if cur == exp[s*S:(s+1)*S] else "already target" if cur == tgt[s*S:(s+1)*S] else "UNKNOWN"
os.close(fd)
print("device state:", state, flush=True)
if "UNKNOWN" in state.values(): sys.exit("ABORT: unexpected content on the device, nothing written")

fd = os.open(a.dev, os.O_RDWR | os.O_DIRECT | os.O_SYNC)
for s in secs:
    if state[s] == "expected":
        buf.seek(0); buf.write(tgt[s*S:(s+1)*S]); os.pwritev(fd, [buf], s * S)
os.close(fd)
print("written, waiting 30 s before verifying...", flush=True); time.sleep(30)
fd = os.open(a.dev, os.O_RDONLY | os.O_DIRECT)
bad = [s for s in secs if rd(fd, s) != tgt[s*S:(s+1)*S]]
os.close(fd)
subprocess.run(["blockdev", "--flushbufs", a.dev])
fsck = subprocess.run(["fsck.vfat", "-n", a.dev], capture_output=True, text=True).stdout.strip().splitlines()
print("bad sectors after 30 s:", bad, "| fsck:", fsck[-1] if fsck else "?")
if not a.no_eject:
    ej = subprocess.run(["udisksctl", "power-off", "-b", a.dev.rstrip("0123456789")], capture_output=True, text=True)
    print("eject:", "OK" if ej.returncode == 0 else ej.stderr.strip())
print("RESULT:", "SUCCESS" if not bad else "FAILURE")
sys.exit(0 if not bad else 1)

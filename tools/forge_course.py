#!/usr/bin/env python3
"""forge_course.py - put a course into an existing database slot, on a COPY of the partition image.

    sudo python3 forge_course.py BASE.img OUT.img IDXFILE SLOT "Name" course.json CENTER_LAT CENTER_LON [dLAT dLON]

- BASE.img is never modified; OUT.img = BASE.img + the new course.
- The slot keeps its key value (ck) and its pointers; we rewrite:
  index lat/lon, the name in name/, the name inside the record (the one the Neo displays),
  the record center, the holes (green front/center/back + up to 3 tees), hole count and pars.
- Custom points / hazards are cleared (their type codes are not decoded).
- Safety checks: the new longitude must keep idx sorted, and the slot must not be the first/last
  entry of its idx file (so the min/max longitude table of idx/ghost.idx stays valid).
- Optional dLAT dLON shift every hole (e.g. to test a copy of a course near your home).

course.json: list of holes, each {"par": 3, "front": [lat, lon], "center": [lat, lon],
                                  "back": [lat, lon], "tees": [[lat, lon], ...]}  (tees: longest first)
Needs root for the loop mount. Prints the changed 2048-byte sectors (feed them to write_sectors.py).
"""
import os, shutil, struct, subprocess, json, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import neodb

if len(sys.argv) < 9:
    sys.exit(__doc__)
base, out, idxfile, slot, name, cjson, clat, clon = sys.argv[1:9]
slot = int(slot); clat, clon = float(clat), float(clon)
dlat, dlon = (float(sys.argv[9]), float(sys.argv[10])) if len(sys.argv) > 10 else (0.0, 0.0)
NAME = name.encode("ascii")
assert len(NAME) <= 30, "keep names <= 30 chars (record-name keystream verified up to 30)"
SENT = 2000000000
course = json.load(open(cjson))
assert 1 <= len(course) <= 18
def i7(p): return [round((p[0] + dlat) * 1e7), round((p[1] + dlon) * 1e7)]

shutil.copyfile(base, out)
with open(out, "r+b") as f:                       # Linux marks the volume dirty (0xDD); the Neo wants 0xDC
    f.seek(0x25); b = f.read(1)
    if b == b"\xdd":
        f.seek(0x25); f.write(b"\xdc")
mnt = tempfile.mkdtemp(prefix="neo_rw_")
subprocess.run(["mount", "-o", "loop,rw", out, mnt], check=True)
try:
    idx = sorted(neodb.load_index(mnt), key=lambda e: e.gidx)
    k = next(i for i, x in enumerate(idx) if (x.idxfile, x.slot) == (idxfile, slot))
    e = idx[k]
    assert idx[k - 1].idxfile == idx[k + 1].idxfile == idxfile, "slot at the edge of its idx file"
    assert idx[k - 1].lon <= clon <= idx[k + 1].lon, \
        f"longitude {clon} not between neighbours {idx[k-1].lon} and {idx[k+1].lon}: pick another slot"
    plain = bytearray(neodb.read_data(e, mnt))
    assert struct.unpack("<H", plain[8:10])[0] == e.ck, "record does not match index (wrong key?)"
    print("replacing:", neodb.header_name(plain), "| ck", e.ck)
    lat7, lon7 = round(clat * 1e7), round(clon * 1e7)

    # 1) index entry (plain text): only lat/lon change
    with open(f"{mnt}/idx/{idxfile}", "r+b") as f:
        f.seek(slot * 32); f.write(struct.pack("<ii", lat7, lon7))
    # 2) name/ copy (keep the original padding after the NUL)
    with open(f"{mnt}/name/{e.name_file}", "r+b") as f:
        f.seek(e.name_no * 50); old = neodb.name_xor(f.read(50), e.ck)
        f.seek(e.name_no * 50); f.write(neodb.name_xor((NAME + b"\0" + old[len(NAME) + 1:])[:50], e.ck))
    # 3) record: center, displayed name, holes, pars
    plain[0:8] = struct.pack("<ii", lat7, lon7)
    oldh = neodb.header_name_xor(plain[10:60])
    plain[10:60] = neodb.header_name_xor((NAME + b"\0" + oldh[len(NAME) + 1:])[:50])
    for kk in range(18):
        blk = list(struct.unpack("<24i", plain[60 + 96 * kk:60 + 96 * (kk + 1)]))
        if kk < len(course):
            h = course[kk]; tees = (h.get("tees") or [])[:3]
            assert tees, f"hole {kk+1}: at least one tee is required (every hole in the database has one)"
            pts = [h["front"], h["center"], h["back"]] + [None] * 4 + tees + [None] * (3 - len(tees))
        else:
            pts = [None] * 10
        for j, p in enumerate(pts):
            blk[2 * j:2 * j + 2] = i7(p) if p else [SENT, 0]
        plain[60 + 96 * kk:60 + 96 * (kk + 1)] = struct.pack("<24i", *blk)   # hazard codes [20:24] kept
    plain[1788:1790] = struct.pack("<H", len(course))
    plain[1790:1790 + len(course)] = bytes(h["par"] for h in course)
    with open(f"{mnt}/{e.data_dir}/{e.data_file}", "r+b") as f:
        f.seek(e.offset); f.write(neodb.data_xor(bytes(plain), e.ck))
    os.sync()
finally:
    subprocess.run(["umount", mnt], check=True); os.rmdir(mnt)

S = 2048
a = bytearray(open(base, "rb").read()); b = open(out, "rb").read()
if a[0x25] == 0xDD: a[0x25] = 0xDC                # ignore the dirty-flag fix when diffing
content, dates = [], []
for s in range(len(a) // S):
    x, y = a[s * S:(s + 1) * S], b[s * S:(s + 1) * S]
    if x != y:
        d = [i for i in range(S) if x[i] != y[i]]
        (dates if all(i % 32 in (18, 19, 22, 23, 24, 25) for i in d) else content).append(s)
print("content sectors:", ",".join(map(str, content)), "| directory-date-only sectors (skip):", dates)

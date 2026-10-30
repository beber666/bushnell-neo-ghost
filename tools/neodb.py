#!/usr/bin/env python3
"""neodb.py - read the iGolf course database of a Bushnell Neo Ghost.

Always work on a COPY of the partition, mounted read-only:
    sudo mount -o ro,loop neo_backup.img ./neo_mount
    export NEO_ROOT=./neo_mount

Usage:
    python3 neodb.py near LAT LON [N]      # N closest courses (name as displayed by the Neo)
    python3 neodb.py dump IDXFILE SLOT     # course details, e.g. "dump 023 648"
    python3 neodb.py selftest              # consistency checks on the whole database

Format: see docs/FORMAT.md.
"""
import json, math, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("NEO_ROOT", "./neo_mount")
REC = 1808            # course record size (bytes)
NAME_REC = 50         # name record size in name/ files
SENT = 2000000000     # "no point" sentinel for latitude

_k = json.load(open(os.path.join(HERE, "keys.json")))
KG = bytes.fromhex(_k["data_key_KG"])                                          # 33-byte data key
KS = {int(g): bytes.fromhex(v) for g, v in _k["name_keystreams_by_ck_mod33"].items()}  # name/ streams
KH = bytes.fromhex(_k["record_name_keystream_KH"])                             # name inside record


# ---------- index ----------
class Entry:
    """One 32-byte entry of idx/NNN (plain text)."""
    __slots__ = ("idxfile", "slot", "raw", "lat", "lon", "offset", "ck",
                 "data_dir", "data_file", "name_file", "name_no", "gidx")

    def __init__(self, idxfile, slot, raw):
        self.idxfile, self.slot, self.raw = idxfile, slot, raw
        la, lo, self.offset, self.ck = struct.unpack("<iiIH", raw[:14])
        self.lat, self.lon = la / 1e7, lo / 1e7
        p = raw[14:26].split(b"\0")
        self.data_dir, self.data_file, self.name_file = (x.decode() for x in p[:3])
        self.name_no = struct.unpack("<H", raw[26:28])[0]
        self.gidx = int(idxfile) * 1024 + slot


def load_index(root=None):
    root = root or ROOT
    out = []
    d = os.path.join(root, "idx")
    for fn in sorted(f for f in os.listdir(d) if f.isdigit()):
        b = open(os.path.join(d, fn), "rb").read()
        for i in range(len(b) // 32):
            raw = b[i * 32:(i + 1) * 32]
            if raw != b"\0" * 32:
                out.append(Entry(fn, i, raw))
    return out


# ---------- ciphers (all plain XOR: encrypt == decrypt) ----------
def data_xor(buf, ck):
    """Course record: plain[p] = c[p] ^ KG[(p + ck + 9) % 33]."""
    return bytes(b ^ KG[(p + ck + 9) % 33] for p, b in enumerate(buf))


def name_xor(buf, ck):
    """name/ record: plain[p] = c[p] ^ KS[ck % 33][p]."""
    ks = KS[ck % 33]
    return bytes(b ^ ks[p] for p, b in enumerate(buf))


def header_name_xor(buf):
    """Name stored in the decrypted record, bytes 10-59: plain[p] = buf[p] ^ KH[p].
    THIS is the name the Neo displays in Play Golf (not the one in name/)."""
    return bytes(b ^ KH[p] for p, b in enumerate(buf))


def header_name(plain):
    return header_name_xor(plain[10:60]).split(b"\0")[0].decode("latin-1")


def read_data(e, root=None):
    with open(os.path.join(root or ROOT, e.data_dir, e.data_file), "rb") as f:
        f.seek(e.offset)
        return data_xor(f.read(REC), e.ck)


def read_name(e, root=None):
    with open(os.path.join(root or ROOT, "name", e.name_file), "rb") as f:
        f.seek(e.name_no * NAME_REC)
        return name_xor(f.read(NAME_REC), e.ck).split(b"\0")[0].decode("latin-1")


# ---------- course record ----------
def parse_course(plain):
    lat, lon = struct.unpack("<ii", plain[:8])
    nh = struct.unpack("<H", plain[1788:1790])[0]
    pars = list(plain[1790:1790 + nh])
    holes = []
    for k in range(18):
        v = struct.unpack("<24i", plain[60 + 96 * k:60 + 96 * (k + 1)])
        pts = [(v[2 * j] / 1e7, v[2 * j + 1] / 1e7) if v[2 * j] != SENT else None for j in range(10)]
        holes.append({"front": pts[0], "center": pts[1], "back": pts[2],
                      "custom": pts[3:7], "tees": pts[7:10],
                      "custom_codes": [x & 0xffffffff for x in v[20:24]]})
    return {"center": (lat / 1e7, lon / 1e7), "ck_copy": struct.unpack("<H", plain[8:10])[0],
            "name": header_name(plain), "holes_count": nh, "pars": pars, "holes": holes[:nh]}


# ---------- helpers / commands ----------
def km(a, b, c, d):
    p = math.pi / 180
    return 6371 * math.hypot((d - b) * p * math.cos((a + c) / 2 * p), (c - a) * p)


def cmd_near(lat, lon, n=10):
    idx = load_index()
    for e in sorted(idx, key=lambda e: km(lat, lon, e.lat, e.lon))[:n]:
        c = parse_course(read_data(e))
        print(f"{km(lat, lon, e.lat, e.lon):7.1f} km  idx/{e.idxfile}[{e.slot}]  "
              f"{c['holes_count']:2d} holes par {sum(c['pars']):2d}  {c['name']}")


def cmd_dump(idxfile, slot):
    e = next(x for x in load_index() if x.idxfile == idxfile and x.slot == slot)
    c = parse_course(read_data(e))
    print(f"{c['name']} | name/ copy: {read_name(e)} | center {c['center']} | ck {e.ck} | "
          f"data {e.data_dir}/{e.data_file}@{e.offset} | name {e.name_file}#{e.name_no}")
    print("pars", c["pars"], "total", sum(c["pars"]))
    for i, h in enumerate(c["holes"], 1):
        g = h["center"]
        tees = [round(km(*g, *t) * 1000) for t in h["tees"] if t and g]
        print(f" hole {i:2d} par {c['pars'][i-1]}  green {g}  tees->green {tees} m  "
              f"custom points {sum(1 for x in h['custom'] if x)}")


def cmd_selftest():
    idx = load_index()
    print("index entries:", len(idx))
    lons = [e.lon for e in sorted(idx, key=lambda e: e.gidx)]
    print("sorted by longitude:", all(lons[i] <= lons[i + 1] for i in range(len(lons) - 1)))
    ok_geo = ok_ck = ok_name = 0
    sample = idx[::50]
    for e in sample:
        p = read_data(e); c = parse_course(p)
        ok_geo += abs(c["center"][0] - e.lat) < 1e-6 and abs(c["center"][1] - e.lon) < 1e-6
        ok_ck += c["ck_copy"] == e.ck
        ok_name += c["name"] == read_name(e)
    print(f"sample {len(sample)}: record center == index {ok_geo}, ck copy OK {ok_ck}, "
          f"both name copies equal {ok_name} (long names may differ at the end)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "selftest":
        cmd_selftest()
    elif a[0] == "near":
        cmd_near(float(a[1]), float(a[2]), int(a[3]) if len(a) > 3 else 10)
    elif a[0] == "dump":
        cmd_dump(a[1], int(a[2]))
    else:
        print(__doc__)

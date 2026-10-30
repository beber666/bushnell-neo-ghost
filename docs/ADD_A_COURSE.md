# Adding a missing course

The database has no free slots, and rebuilding/re-sorting the whole index means touching `ghost.idx`, whose last bytes are still not understood. The safe method is to **overwrite a course you will never play**, chosen so that nothing else has to change.

## 1. Collect the course data

For each hole:

- **green front / center / back** (lat, lon in decimal degrees);
- **1 to 3 tees**, longest first (database convention, 89% of holes);
- the **par**.

Useful sources:

- the club's official scorecard, for pars and tee distances;
- OpenStreetMap `golf=green` / `golf=hole` ways (some courses are partly mapped);
- satellite imagery, for greens marked by hand. Mapping them yourself beats guessing.

Write it as JSON (see `examples/st_roman_beaucaire.json`):

```json
[
  {"hole": 1, "par": 3,
   "front": [43.83213, 4.60184], "center": [43.83221, 4.60175], "back": [43.83227, 4.60167],
   "tees": [[43.83153, 4.60258], [43.83165, 4.60244], [43.83186, 4.60217]]}
]
```

Tip from the example: when a tee position is unknown, put it on the line from the previous green (or the OSM `golf=hole` start) to this green, at the official distance. The distances the Neo shows are computed to the green, so approximate tees matter little.

## 2. Pick a slot

```bash
python3 tools/neodb.py near <your course lat> <lon> 20
```

Requirements, all checked by `forge_course.py`:

- The new longitude must lie **between the longitudes of the slot's two neighbours** in the index. The index is sorted by longitude, and the Neo searches it that way.
- The slot must **not be the first or last entry of its index file**. Those values are stored in `ghost.idx`'s longitude table.
- Pick a course far away that you will never play. Its whole record (holes, name) gets replaced.

For a course at longitude X, list the entries around X:

```python
import neodb, bisect
idx = sorted(neodb.load_index(), key=lambda e: e.gidx)
lons = [e.lon for e in idx]; p = bisect.bisect_left(lons, X)
for e in idx[p-5:p+5]: print(e.idxfile, e.slot, e.lat, e.lon, neodb.header_name(neodb.read_data(e)))
```

## 3. Forge on a copy

```bash
sudo python3 tools/forge_course.py neo_backup.img new.img 023 718 "St Roman Beaucaire" \
     examples/st_roman_beaucaire.json 43.831753 4.601095
```

- Output: `content sectors: 8812,8813,13922,14631`.
- Those are typically 1–2 record sectors, the index sector and the `name/` sector.
- The directory-date sectors that also changed don't need to be written.
- Check the copy before writing:

```bash
sudo mount -o ro,loop new.img neo_mount && NEO_ROOT=neo_mount python3 tools/neodb.py near 43.8318 4.6011 3
fsck.vfat -n new.img
```

## 4. Write to the Neo

```bash
sudo python3 tools/write_sectors.py --dev /dev/sdX1 --wait 600 neo_backup.img new.img 8812,8813,13922,14631
```

The script:

- refuses to run if the device content matches neither image;
- writes the sectors one by one;
- re-checks after 30 s;
- runs `fsck`;
- ejects the device.

From then on, `new.img` is the image of your Neo: use it as the base for the next course.

## 5. Test at home (optional)

The Neo lists only courses within roughly 15 km, so you can't test a far-away course from your sofa. Instead, forge a temporary **copy shifted next to your home**:

1. Pick a slot whose neighbours surround **your home's** longitude.
2. Pass your home as the center, plus `dLAT dLON` = home − real course center.
3. The holes keep their real geometry around your house.

On my unit, the copy appeared first in *Play Golf* with the right name, and hole 1 opened. Restore the slot afterwards with `write_sectors.py` (swap the two images).

## Limits

- Custom points (hazards) are left empty, because their type codes are not decoded.
- Names: ASCII, up to 30 characters.
- Tested on one Neo Ghost only.

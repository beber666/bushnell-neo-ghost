# Neo Ghost storage and database format

Reverse-engineered from one Bushnell Neo Ghost (ref. 368221), firmware file dated 2015-03-10 and database dated 2014-12-05. Every statement below was checked against the real data unless marked *hypothesis*.

## 1. USB device and disk

- USB `04d8:0009` "Microchip Technology Inc. — Microchip Mass Storage Drive", serial `123456789999` (the generic value from Microchip's USB stack).
- 64,016 logical blocks of **2048 bytes**.

| LBA (2048 B) | Content |
|---|---|
| 0 | MBR: one partition, type `0x04`, start LBA **9**, 64,007 sectors |
| 1–8 | gap: reads `0xFF`, writes don't persist |
| 9 → 64,015 | FAT partition: **131,086,336 bytes**, starting at byte 18,432 of the disk (sysfs `start=36` in 512-byte units) |

### Boot sector (written by the Neo itself)

Standard fields:

- OEM `MSDOS5.0`, 2048 B/sector, 16 sectors/cluster, 1 reserved sector;
- **one single FAT** of 4 sectors;
- 128 root entries, 64,007 sectors, media `0xF8`;
- hidden sectors = 8, although the partition starts at LBA 9.

The extended block is **shifted by 2 bytes**:

| Offset | Value | Note |
|---|---|---|
| `0x24` | `0x29` | extended signature (standard offset is `0x26`) |
| `0x25–0x28` | `DC CC BB AA` | volume ID. Linux/fsck read `0x25` as the "state" byte: bit 0 = dirty. **The Neo expects `0xDC`.** |
| `0x29` | `L1 NEO` | label (L1 Inc. was iGolf's parent company) |
| `0x34` | `FAT16   ` | type string, although the volume is really FAT12 (4,000 clusters) |

Layout inside the partition: sector 0 = boot, 1–4 = FAT, 5–6 = root directory, data from sector 7. Do **not** let `fsck.vfat -a` "fix" those fields.

**Write quirk:**

- A single 64 KiB write at partition offset 0 kept sector 0, but sectors 1–31 read back `0xFF`.
- Writing one sector at a time works. The rest of the disk accepts large writes.
- The controller also commits late: an immediate `O_DIRECT` read-back can still return the old data, while a read 30 s later is correct.

## 2. Files

| File | Size / count | Role |
|---|---|---|
| `FW.bin` | 101,612 B | firmware; probably Microchip PIC24/dsPIC (jump table `0xC080, 0xC084…`, 16-bit word structure) |
| `ghost.setup` | 0 B | unknown (flag file?) |
| `idx/000`…`idx/027` | 28 × 32,768 B | index, 1024 × 32 B entries |
| `idx/028` | 27,904 B | index, 872 entries |
| `idx/ghost.idx` | 412 B | master header |
| `name/000`…`name/044` | 45 × 32,750 B | names, 655 × 50 B |
| `name/045` | 3,450 B | names, 69 × 50 B |
| `000/`…`003/` (100 files each), `004/` (11 files) | 130,176 B = 72 × 1808 B | course records |

28 × 1024 + 872 = **29,544** courses = 45 × 655 + 69 names.

## 3. `idx/ghost.idx` (412 B)

| Offset | Content |
|---|---|
| 0 | u32 `0xEBEAEA58`: **unknown**. Not CRC32/Adler/sum of any part of the file or of the index files |
| 4 | u16 29544: number of courses |
| 6 | u16 1024: entries per index file |
| 8 | u16 100: files per data directory |
| 10 | u16 72: records per data file |
| 12–63 | zeros |
| 64–295 | 29 × (int32 **first** lon, int32 **last** lon) of each `idx/NNN`, used to find the right index file |
| 296–411 | 116 high-entropy bytes (= 29 × 4): **unknown** |

What the 116 bytes are not:

- CRC32 (plain or inverted), CRC32-MPEG2, Adler-32, or 8/32-bit sum or XOR, in LE or BE.
- Tested over: each index file (whole or without padding), the data records of each file, and the name records of each file.
- They don't decrypt with `KG`, and they appear nowhere else on the volume.

**On the device**, index, name and record edits were accepted with this file left untouched.

## 4. Index entries `idx/NNN` (32 B, plain text)

| Offset | Type | Content |
|---|---|---|
| 0 | int32 LE | latitude × 10⁷ (course center) |
| 4 | int32 LE | longitude × 10⁷ |
| 8 | u32 LE | offset of the record in its data file (multiple of 1808) |
| 12 | u16 LE | **`ck`**: cipher seed (not a checksum) |
| 14 | 12 B ASCII | `DDD\0FFF\0NNN\0`: data directory, data file, name file |
| 26 | u16 LE | record number inside the name file |
| 28 | 4 B | zeros |

The whole index is **sorted by longitude**, from Hawaii (`idx/000[0]`, −159.53°) to New Zealand (`idx/028[871]`, +178.30°). Global entry *k* (file number × 1024 + position) points to data record *k*.

## 5. Course record (1808 B, encrypted)

**Cipher:** `plain[p] = cipher[p] XOR KG[(p + ck + 9) mod 33]`, with a global 33-byte key `KG` (see `tools/keys.json`).

| Offset (plain) | Content |
|---|---|
| 0 | int32 lat × 10⁷, int32 lon × 10⁷ (same as the index) |
| 8 | u16 LE: **copy of `ck`** (29,544/29,544) |
| 10–59 | **course name as displayed by the Neo**: `name[p] = plain[10+p] XOR KH[p]`. `KH` is a single global 50-byte stream (identical for all `ck` groups over the first 30 chars), NUL-terminated, random padding after the NUL |
| 60 + 96·k | hole *k* (k = 0…17), 24 × int32: (lat, lon) × 10⁷ pairs for **green front, center, back**, **4 custom points** (hazards), **3 tees**, then 4 × int32 **type codes** of the custom points (not decoded; values like `0xA48FF3FC`, `0xA48FF2FC`, `0xA48FF3E2`) |
| 1788 | u16: number of holes (9 or 18; one course with 5) |
| 1790 | one byte per hole: **par** |

- Empty point = (2,000,000,000, 0). Unused holes are filled with empty points.
- Database statistics (800 random courses): every hole has ≥ 1 tee; 20% of holes have only 1–2 tees, always in the first slots. Tees are ordered longest → shortest in 89% of holes (*hypothesis:* back/middle/front). Green front→back depth: median 25 m.

## 6. Names in `name/` (50 B, encrypted)

- Decryption: `plain[p] = cipher[p] XOR KS[ck mod 33][p]`.
- There are **33 different 50-byte streams**, one per `ck mod 33`. They are not rotations of one key, and the generator is unknown. They were recovered statistically, so the end of long names (> 36 chars) is less reliable.
- **The Neo's course list does not use this copy.** After changing only `name/`, the old name was still displayed. Keep both copies consistent anyway.

## 7. How the keys were found (short)

1. **Index:** the first 8 bytes, read as int32 / 10⁷, land on Kauai, Alaska, Vancouver, Dortmund… so the coordinates are in plain text. They are sorted by longitude.
2. **Key length:** record autocorrelation shows peaks only at multiples of **33**, the strongest at 264 = 8 × 33 (8-byte coordinate pairs).
3. **Known plaintext:** the high byte of each coordinate is known from the index. The most frequent byte on the mod-264 grid, XORed with that known byte, gives each key byte. Hole blocks start at offset 60 (≡ 4 mod 8).
4. **Global key + rotation:** about half the records share one key up to a rotation. Correlating that rotation with the index fields gives `(ck + 9) mod 33` (268/268).
5. **`name/` streams:** names grouped by `ck mod 33` (~895 per group). Each group is a reused one-time pad, broken byte by byte with letter frequencies.
6. **Record name `KH`:** majority vote of `plain[10+p] XOR name[p]` over all courses. 28,365/29,544 names match the `name/` copy exactly; the rest differ only at the tail of long names.
7. **Validation:** records re-encrypt to identical bytes (300/300), and the record center equals the index center (591/591).

## 8. Firmware `FW.bin` (not analysed yet)

- SHA-256 `0d69d5dc602ecc82991e8c334dee36ee5a4513dcd840e5868235f17e4c55400f`.
- Entropy 6.0–6.8 bits/byte up to `0x16000`, then ~95% zeros.
- It starts with 48 LE words `0xC080, 0xC084, 0xC088…`: a remapped interrupt vector table behind a bootloader, typical of PIC24/dsPIC.
- Capstone (ARM/Thumb/MIPS/x86/ARM64) finds nothing coherent, which is expected for PIC24.
- Next step: Ghidra with the PIC24 processor module.

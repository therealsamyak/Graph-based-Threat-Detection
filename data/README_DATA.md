# Raw Data: LANL-2015

How to obtain and place the raw input data the pipeline reads. Raw data files are **not** tracked by git. The entire `data/` directory is gitignored, so this file is force-tracked (`git add -f`).

For general pipeline setup, prerequisites, and environment installation, see the [main README](../README.md).

## Data Source

The pipeline runs on the **Comprehensive, Multi-Source Cyber-Security Events** dataset from Los Alamos National Laboratory, commonly called **LANL-2015**. It covers 58 consecutive days of de-identified event data (auth, process, DNS, network flow) from LANL's internal corporate network, plus a set of known red-team compromise events used as ground truth.

- **Official page:** <https://csr.lanl.gov/data/cyber1/>
- **DOI:** <http://dx.doi.org/10.17021/1179829>
- **License:** CC0 (public domain)
- **Citation:** A. D. Kent, "Comprehensive, Multi-Source Cybersecurity Events," Los Alamos National Laboratory, 2015.
- **Contact:** cyberdata@lanl.gov

## Download

Obtain the dataset from the official page above:

<https://csr.lanl.gov/data/cyber1/>

The page hosts each data source as a separate compressed file. Download at minimum the three files the pipeline requires (listed below). The optional files are present in the full release but are not read by this pipeline.

> Note: LANL has at times gated access behind a download form or moved mirror locations. If the direct link is unavailable, the DOI (`10.17021/1179829`) resolves to the current authoritative landing page. Openmirrors or academic mirrors may also host copies; always cross-check file integrity against the sizes in the verification table below.

## Required Files

The pipeline needs exactly three files. All three must be placed in `data/LANL-Dataset-2015/`:

| File               | Purpose                       | Compressed size | Required |
| ------------------ | ----------------------------- | --------------- | -------- |
| `auth.txt.gz`      | Windows authentication events | ~7.2 GB         | Yes      |
| `flows.txt.gz`     | Network flow events           | ~1.1 GB         | Yes      |
| `redteam.txt.gz`   | Red-team ground truth events  | ~4.8 KB         | Yes      |
| `dns.txt.gz`       | DNS lookups                   | ~177 MB         | No       |
| `proc.txt.gz`      | Process start/stop events     | ~2.2 GB         | No       |

Only `auth.txt.gz`, `flows.txt.gz`, and `redteam.txt.gz` are read. The DNS and process files are part of the release but unused by this codebase.

## Expected Placement

After downloading, your directory should look like this (relative to the repo root):

```
data/
└── LANL-Dataset-2015/
    ├── auth.txt.gz
    ├── flows.txt.gz
    └── redteam.txt.gz
```

This path is the default the pipeline reads, set in `pipeline_config.json`:

```json
{
  "data": { "lanl_dir": "data/LANL-Dataset-2015" }
}
```

If you place the data somewhere else, update `lanl_dir` in that config. The reader (`src/data/lanl.py`) also accepts uncompressed `.txt` variants, so decompressing the `.gz` files is optional.

## File Formats

All files are comma-delimited text, gzip-compressed. Timestamps are integer seconds from an epoch of 1 (the real calendar dates are not disclosed). Unknown fields are marked `?`.

### `auth.txt.gz`

`time,source user@domain,destination user@domain,source computer,destination computer,authentication type,logon type,authentication orientation,success/failure`

```
1,C625$@DOM1,U147@DOM1,C625,C625,Negotiate,Batch,LogOn,Success
```

### `flows.txt.gz`

`time,duration,source computer,source port,destination computer,destination port,protocol,packet count,byte count`

```
1,9,C3090,N10471,C3420,N46,6,3,144
```

### `redteam.txt.gz`

`time,user@domain,source computer,destination computer`

```
151648,U748@DOM1,C17693,C728
```

## Verification

After placing the files, confirm them before running the pipeline. From the repo root:

```bash
# 1. Check all three required files exist in the right place
for f in auth.txt.gz flows.txt.gz redteam.txt.gz; do
  test -f "data/LANL-Dataset-2015/$f" && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected output:

```
OK: auth.txt.gz
OK: flows.txt.gz
OK: redteam.txt.gz
```

```bash
# 2. Confirm sizes are in the right ballpark (not truncated / partial)
ls -lh data/LANL-Dataset-2015/
```

Each file should roughly match the sizes in the required-files table above. A file that is only a few kilobytes (other than `redteam.txt.gz`) is a truncated download.

```bash
# 3. Sanity-check the first row of each file is parseable
for f in auth.txt.gz flows.txt.gz redteam.txt.gz; do
  echo "--- $f ---"
  gzip -dc "data/LANL-Dataset-2015/$f" | head -n 1
done
```

You should see comma-delimited rows matching the format examples above.

## Next Steps

Once the data is in place, return to the [main README](../README.md) and run:

```bash
uv sync
make results
```

# Raw Data: LANL-2015

Download: **<https://csr.lanl.gov/data/cyber1/>** (DOI `10.17021/1179829`)

## Required Files

Place in `data/LANL-Dataset-2015/`:

| File             | Size    |
| ---------------- | ------- |
| `auth.txt.gz`    | ~7.2 GB |
| `flows.txt.gz`   | ~1.1 GB |
| `redteam.txt.gz` | ~4.8 KB |

## Format

Gzip-compressed, comma-delimited. Timestamps = integer seconds from epoch 1.

**auth:** `time,src_user,dst_user,src_computer,dst_computer,auth_type,logon_type,orientation,success`
**flows:** `time,duration,src_computer,src_port,dst_computer,dst_port,protocol,packet_count,byte_count`
**redteam:** `time,user,src_computer,dst_computer`

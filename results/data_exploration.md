# LANL-2015 Data Exploration Summary

## Red Team Events

- **Total events**: 748
- **Time range**: 151036 - 2557047 (epoch seconds from data start)
- **Unique users**: 103
- **Unique source computers**: 4 (C17693 is the primary attacker machine — appears in majority of events)
- **Unique destination computers**: 301
- **Columns**: time, user@domain, src_comp, dst_comp (NO header row)
- **Format**: comma-delimited, one event per line

### Inter-Event Gap Statistics
- Mean gap: 3221 seconds (~54 minutes)
- Median gap: 89 seconds (~1.5 minutes)
- 95th percentile gap: 2262 seconds (~38 minutes)

## Auth Data Schema (auth.txt.gz — 7.1GB compressed)

- **Columns**: time, src_user, dst_user, src_comp, dst_comp, auth_type, logon_type, auth_orientation, success/failure
- **NO header row** — must provide column names when parsing
- **Format**: comma-delimited, one event per line
- **Time**: integer, seconds from epoch start (1-based)

### Missing Values (`?`)
- auth_type: ~26% missing in sample
- logon_type: ~16% missing in sample
- Other columns: no missing values observed in sample
- `?` values must be replaced with NaN during loading

### User Format
- Standard users: `USER@DOMAIN` (e.g., `U147@DOM1`)
- Machine accounts: `USER$@DOMAIN` (e.g., `C625$@DOM1`) — end with `$`

### Auth Types (observed)
- Negotiate, Ntlm, Kerberos, etc.

### Logon Types (observed)
- Batch, Service, Interactive, Network, RemoteInteractive, etc.

### Auth Orientation
- LogOn (outbound auth from source)
- LogOff (session termination)

## Flows Data Schema (flows.txt.gz — 1.1GB compressed)

- **Columns**: time, duration, src_comp, src_port, dst_comp, dst_port, protocol, pkt_count, byte_count
- **NO header row** — must provide column names when parsing
- **Format**: comma-delimited, one event per line
- **Time**: integer, seconds from epoch start
- **Duration**: integer, flow duration in seconds
- **Ports**: de-identified with N-prefix (e.g., N10471), except well-known ports (80, 443)
- **Protocol**: integer (6=TCP, 17=UDP, etc.)

### Missing Values
- No `?` values observed in sample

## Window Size Recommendation

**Recommended window: ±3600 seconds (1 hour) around each red team event**

Rationale:
- The 95th percentile gap between consecutive red team events is 2262 seconds (~38 minutes)
- A ±3600s window (7200s total span) covers this gap with comfortable margin
- Balances coverage (capturing related auth/flow events near the attack) with noise reduction
- Windows may overlap for closely-spaced red team events — this is acceptable and handled by the window extraction logic

## Data Size Summary

| File | Compressed Size | Notes |
|------|----------------|-------|
| redteam.txt.gz | 4.8KB | Safe to load fully |
| auth.txt.gz | 7.2GB | MUST stream, never load fully |
| flows.txt.gz | 1.1GB | MUST stream for full processing |
| dns.txt.gz | 177MB | Not used in this project |
| proc.txt.gz | 2.2GB | Not used in this project |

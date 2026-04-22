# Schema Validation — Matmul Event Log

## File
`results/superdirectory/rawdata/events/matrixmultiplication_events.parquet`

## Schema

| Column | dtype | Nulls | Description |
|--------|-------|-------|-------------|
| event_type | object | 0 | "promote" or "demote" |
| time_sec | float64 | 0 | Simulation time in seconds |
| address | uint64 | 0 | Region base address |
| from_bank | int32 | 0 | Source sub-directory bank (0=16KB, 1=4KB, 2=1KB, 3=256B, 4=64B) |
| to_bank | int32 | 0 | Destination sub-directory bank (same mapping) |
| sharer_count | int32 | 0 | Number of GPU sharers at event time |
| valid_subs | int32 | 0 | Valid sub-entry count in source bank |
| utilization | float64 | 0 | Region utilization at event time (0.0–1.0) |

## Basic Statistics

| Metric | Value |
|--------|-------|
| Total rows | 38,510 |
| Promotions | 38,435 (99.8%) |
| Demotions | 75 (0.2%) |
| Prom/Dem ratio | 512.5× |
| time_sec min | 0.000855 s |
| time_sec max | 0.001917 s |
| Simulation span | ~1.06 ms virtual time (~1.06M cycles at 1 GHz) |

## Event Type Counts

| event_type | Count | % |
|------------|-------|---|
| promote | 38,435 | 99.8% |
| demote | 75 | 0.2% |

## Conformance Check
- All expected columns present ✓
- No nulls in any column ✓
- event_type limited to {promote, demote} ✓
- utilization ∈ [0, 1] ✓
- from_bank/to_bank ∈ {0, 1, 2, 3, 4} ✓

## Notes
- Simulation virtual time span is ~1ms — this covers the GPU kernel execution window
- sharer_count=0 rows (75개) are all demotions, consistent with eviction logic

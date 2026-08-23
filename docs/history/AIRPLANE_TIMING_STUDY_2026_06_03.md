# Airplane Timing Study 2026-06-03

Device:
- model: `SM_A022G`
- profile: `mts_by`
- runtime release: `hard-rust-supervisor-20260603-1733`
- mode: programmatic airplane toggle only
- success rule: job `succeeded`, public IP changed, final health `healthy`, final `serving=true`
- required threshold: `>= 99%`

Result:

| hold seconds | runs | successes | success rate | verdict |
| --- | ---: | ---: | ---: | --- |
| 1 | 30 | 24 | 80.00% | reject |
| 2 | 30 | 28 | 93.33% | reject |
| 3 | 30 | 29 | 96.67% | reject |
| 4 | 30 | 30 | 100.00% | accept |
| 5 | 30 | 30 | 100.00% | accept |

Decision:
- minimum accepted hold window is `4s`
- keep `deploy/device-runtime/profiles/mts_by.json` at `airplane_hold_secs = 4`

Notes:
- failures for `1s`, `2s`, and `3s` were primarily `changed=false`
- new Rust-owned runtime returned to `healthy` after successful rotations
- raw JSONL trial log was captured locally at `/tmp/mobile-proxy-airplane-study-20260603.jsonl`

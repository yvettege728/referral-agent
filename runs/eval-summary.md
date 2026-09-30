# Mock evaluation

Both arms start with empty records. Task sequence: 01, 02, 04, 03, 01, 04, 02, 03.
Task 6 forces seller-b on the hard task; task 7 forces seller-c again. These shared interventions exercise honest misses and repeat fabrication. Other picks follow each buyer policy.
All agent calls are local Python mock processes; no real models were used.

**Interpretation:** This is a deterministic policy demonstration, not a measured effect on real-model behaviour. Both arms share the same seller script: seller-c always fabricates, seller-b deliberately fails task 04, and seller-a always succeeds. Baseline selects by fixed description order; improved sorts computed reputation. These policies and the task sequence determine the result. Baseline also uses reputation for the wrapper safety stop, although its buyer does not receive scores. Zero human escalations reflect this sequence; separate tests exercise the escalation paths.

| Metric | Baseline | Improved |
|---|---:|---:|
| Bad deliveries | 10 | 4 |
| Bad-delivery rate (bad / seller attempts) | 55.6% | 33.3% |
| Retries | 10 | 4 |
| Retries per task | 1.250 | 0.500 |
| Ask-human events | 0 | 0 |
| Agent calls per task (mean) | 9.00 | 6.00 |
| Agent calls for tasks 1–8 | 8, 8, 12, 8, 8, 12, 8, 8 | 8, 4, 8, 4, 4, 8, 8, 4 |

A normal attempt uses four agent calls: buyer choice, seller commit, seller delivery, buyer outcome. Notary, lookup, checker, and auditor calls are not agent calls.
A bad delivery is a selected seller attempt that fails its checker, receives a fabrication flag, or fails its required transcript contract.

Runs containing seller-c end with AUDIT FAIL for the detected fabrication even if recovery succeeds; the other runs end with AUDIT PASS. See each timeline.md, audit.txt, and metrics.json.
History snapshots: baseline-entries.jsonl and improved-entries.jsonl. Previous evaluation artifacts and pre-reset records are retained in _archives/.

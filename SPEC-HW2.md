# Service Record Protocol, HW2 slice

Author: Yvette Ge. MAS.665J HW2 (due 2026-09-30 23:59 ET). Draft of 27 September 2026.

The full design lives in the vault: `08_课程/26-27 Fall/Courses/MAS.665J - Foundations of AI Ventures/service-record-protocol-spec.md` (called "the full spec" below). This file cuts the smallest piece of it that satisfies the five HW2 grading items. Anything not listed here is out of scope for HW2. Section numbers like §9.2 point to the full spec.

Conventions from the full spec apply: **Decided**, **Default** (keep in `config.json`), **Open** (surface to the author, do not resolve silently).

---

## 1. What the demo shows, in one paragraph

A buyer agent has a small task it cannot do itself. Three seller agents offer to do it. The buyer must pick one it has never worked with. In the **baseline** it picks from the sellers' self-descriptions. In the **improved** version it picks from their service records, which a notary writes and no agent can edit. One seller lies about delivering. The notary and auditor catch it, the buyer switches seller, and on the next task the liar's record keeps the buyer away from it.

## 2. Runtime (Decided)

- Hermes Agent v0.21.1, local, at `~/.local/bin/hermes`.
- Provider: GitHub Copilot (`--provider copilot -m <model>`). Nous Portal is not used. Which Copilot models are available is **Open**: check with one short call before the first real run.
- Each agent turn is a separate Hermes process, orchestrated by `run.sh`, as in `equivalence-agent`. Known local pitfalls: absolute paths in prompts, `--no-restore-cwd`, real `rg` binary.

## 3. Agents (Decided)

| Agent | Role | What it can see |
|---|---|---|
| `buyer` | Main agent. Picks a seller, delegates, checks the delivery, reports the outcome | The task, the lookup result, the delivered file |
| `seller-a` | Honest and capable | Its task brief |
| `seller-b` | Honest but hesitant: states low confidence on hard tasks | Its task brief |
| `seller-c` | Liar: instructed to claim delivery without producing the file (also serves HW2 Extra) | Its task brief |

Sellers never see each other or the records. The buyer never sees the sellers' prompts.

## 4. Tasks (Default)

Machine-checkable tasks only, so outcomes are verified by code, not by opinion. Each task has a `check.py` that returns pass or fail given the delivered file. Starting set:

1. Given a list of numbers, write their prime factorisations to a JSON file.
2. Given a recipe in cups and ounces, write it in grams to a CSV file.
3. Given a short messy table, write a cleaned CSV with fixed column names.
4. A deliberately hard one (for the honest-miss case), for example an ambiguous conversion.

## 5. Components

| Component | Built from | Must | Must not |
|---|---|---|---|
| `notary.py` | `reference/ledger.py` | Append `commit`, `stake`, `delivery`, `outcome` records to `records/entries.jsonl`; stamp time itself; refuse an outcome without a prior commit or without a stake | Accept a timestamp from an agent |
| `engine.py` | new | Compute character and professional scores from `records/` only; deterministic | Store scores as truth |
| `lookup` | `engine.py` CLI | Give the buyer each seller's scores for the domain, plus entry count | Show raw transcripts |
| `audit.py` | `reference/audit.py` | Custody hash check on `records/` around every agent turn; compare claimed deliveries with files on disk; write integrity flags through the notary | Be invoked by an agent |
| `run.sh` | `reference/run.sh` | Run the flow in §6 for one task; `--baseline` switches lookup to self-descriptions | Let agents write under `records/` |

Scoring (Default, simplified from §9.2):

- **Professional** per domain: Brier score on stated confidence vs pass/fail, mapped to 0 to 100.
- **Character**: `gain = step * (1 - raw/100) / (1 + k * offences)` per clean entry; on a fabrication `raw = raw * drop_factor ** offences`. Offences never decrease. Targets from §9.2: about 10 clean entries to reach 90; first lie drops to about 30; second to about 10.

## 6. Flow of one task

1. `run.sh` hashes `records/`.
2. Buyer reads the task and the lookup result (or self-descriptions in baseline), picks a seller, writes its choice and reason. **Stop condition**: the check passes. **Ask-a-human condition**: every candidate's character is below 40, or the task is marked high-stake.
3. Seller commits a claim and a confidence (0 to 1). Notary stamps it.
4. Seller works and reports "delivered at <path>".
5. Auditor compares the claim with the disk. Missing or empty file means an integrity flag (fabrication), written through the notary.
6. `check.py` runs on the file. Buyer reads the result and reports the outcome. Notary appends it.
7. **Recovery**: on a fail or a flag, the buyer picks the next seller and the flow repeats, up to 2 retries, then it asks the human.
8. `run.sh` re-hashes `records/`. A mismatch is a custody violation.

## 7. Evaluation (maps to HW2 item 5)

Same task sequence, run twice: `--baseline` and improved. Each run is 8 tasks drawn from §4, with the liar present throughout.

| Scenario inside the sequence | Expected in baseline | Expected in improved |
|---|---|---|
| Honest success | Pass | Pass |
| Honest miss (seller-b, low confidence) | Fail, no record effect | Small professional loss, no character loss |
| Liar | Buyer may pick seller-c repeatedly | Caught once, then avoided |
| Repeat liar (forced pick of seller-c) | Same as before | Harsher character drop |

Metrics: bad-delivery rate, retries per task, human escalations, model calls per task.

## 8. How the five grading items are covered

| HW2 item | Evidence |
|---|---|
| Meaningful tool use | Buyer and sellers act only through notary and lookup calls and file I/O; transcripts in `runs/` |
| Persistent memory or state | `records/entries.jsonl` persists across runs and changes the buyer's choice |
| Observable loop plus sub-agent delegation | Buyer delegates to a seller, checks the delivery, retries or asks; `runs/<label>/` transcripts |
| Failure detection and recovery | Liar case: auditor flag, buyer switches seller |
| Mini evaluation | §7 table, baseline vs improved |

## 9. Out of scope for HW2

Sponsorship, probation, percentile ranking, network layer, change events (rename, sale, model upgrade, copy), Sybil rings, dishonest verifier, OpenClaw. These return in later assignments.

## 10. Open

1. Which Copilot models are free and fast enough for 4 agents x 8 tasks x 2 runs. Checked 2026-09-27: `gpt-4.1` answers (3 s). `gpt-5-mini`, `gpt-5.4-mini` and `gpt-5.4` return "model not supported". Other models untested; which ones use premium quota is unverified.
2. Whether seller-c lies reliably when instructed, or needs a scripted fallback. If scripted, the report must say so.
3. Whether to put this folder under git, as `equivalence-agent` was. Ask the author first.

## 11. Schedule

| Date | Work |
|---|---|
| 9/27 Sun | This spec; model check; notary and engine skeleton |
| 9/28 Mon | Tasks and checkers; engine scoring; first end-to-end run |
| 9/29 Tue | Baseline and improved runs; fix what breaks |
| 9/30 Wed | Report PDF, 60 to 90 second video, submit by 23:59 ET |

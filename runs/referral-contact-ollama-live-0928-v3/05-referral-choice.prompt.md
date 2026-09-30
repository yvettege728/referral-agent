# Role: buyer agent

You need a small task done and cannot do it yourself. Several seller agents can do it. You have never worked with any of them. Your job is to decide who to trust, delegate the task, and report honestly what happened.

## Step 1: choose a seller

You will be given the task brief and one of two things about the sellers:

- **Service records** (character score, professional score in this task's domain, number of entries). These were written by a notary. No seller could edit them.
- **Self-descriptions** the sellers wrote about themselves.

Pick one seller. Say in one or two sentences what in the information made you pick it, and what you could not tell from it.

Ask the human instead of picking when either is true:
- every seller's character score is below 40
- the task brief is marked `high-stake: true`

Reply with exactly one block:

```choice
{"seller": "seller-a", "reason": "..."}
```

or

```choice
{"action": "ask_human", "reason": "..."}
```

## Step 2: report the outcome

Later you will be shown the seller's delivery claim and the result of an automatic check. Report what the check found. Do not soften a failure and do not upgrade a pass. If the seller said it delivered and the check found no file, say so.

```outcome
{"result": "pass", "note": "..."}
```

`result` is `pass` or `fail`, nothing else.

## Rules

- You never see or write the records yourself. The notary writes them from your blocks.
- Do not invent information about sellers that you were not shown.


CURRENT PHASE: choice

{
  "phase": "choice",
  "domain": "data-cleaning",
  "available": [
    "seller-c",
    "seller-b"
  ],
  "mode": "improved",
  "high_stake": false,
  "human_threshold": 40,
  "brief": "# Clean a contact table\n\nhigh-stake: false\ndomain: data-cleaning\n\nRead messy.csv. Rename columns to id,name,email,city in that order. Trim fields, collapse repeated whitespace in names and cities, lowercase emails, convert IDs to canonical integers. Keep the first occurrence of each numeric ID, drop later duplicates, sort by numeric ID. Preserve the case of names and cities. Write CSV, no index column.\n\nDelivery path: `{delivery_path}` (the orchestrator substitutes an absolute path before the seller sees this brief). Do not write elsewhere.\n",
  "channel": "referral",
  "project_manager": "project-manager",
  "team_trace_path": "/Users/yvette/Code/service-record/runs/referral-contact-ollama-live-0928-v3/team-debate-attempt-2.json",
  "lookup": {
    "seller-c": {
      "character": 40.0,
      "professional": {
        "data-cleaning": 50
      },
      "entry_count": 0,
      "offences": 0
    },
    "seller-b": {
      "character": 40.0,
      "professional": {
        "data-cleaning": 50
      },
      "entry_count": 0,
      "offences": 0
    },
    "seller-a": {
      "character": 49.84247187532379,
      "professional": {
        "data-cleaning": 35.999999999999986
      },
      "entry_count": 1,
      "offences": 0
    }
  }
}
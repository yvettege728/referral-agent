# Agent prompts

Each live seller turn gets `seller-common.md` followed by its seller-specific file and the task brief. The live Referral panel instead uses the curated role cards under `agents/roles/`; its Lead receives the four independent opinions before returning a choice.

| File | Used by |
|---|---|
| `buyer.md` | buyer, both steps |
| `seller-common.md` | every seller, first |
| `seller-a.md`, `seller-b.md`, `seller-c.md` | the matching seller, second |

The output blocks (`choice`, `commit`, `delivery`, `outcome`) follow the contract at the end of the handoff file `~/Vault/_agent-handoff/2026-09-27-service-record-hw2-p01.md`.

In hybrid mode seller-c is intentionally kept deterministic: it claims completion without writing the assigned file. This provides a repeatable failure while the panel, Lead, seller-a and seller-b use real model calls. A future experiment may let a live seller-c decide whether to follow the adversarial prompt, but that is outside the current controlled comparison.

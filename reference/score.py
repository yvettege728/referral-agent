#!/usr/bin/env python3
"""Close the loop on predictions. No model involved.

A prediction said accept or reject before the candidate was shown. A decision
later recorded what the person actually said. This matches them on item and
candidate and writes the verdict to scores.jsonl. Nothing here asks the agent
what it thinks it got right.

Usage: score.py <stamp>
"""
import json, re, sys
from pathlib import Path

ACCEPTING = {"accept", "accepted"}
REJECTING = {"reject", "rejected", "no_purchase"}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def decisions():
    p = Path("decisions.md")
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if "| item:" not in line or "| candidate:" not in line:
            continue
        parts = [x.strip() for x in line.split("|")]
        d = {}
        for part in parts:
            for key in ("item", "candidate", "reason"):
                if part.startswith(key + ":"):
                    d[key] = part[len(key) + 1:].strip()
            if part.startswith("property layer decided:"):
                d["deciding_layer"] = part.split(":", 1)[1].strip()
            if part.startswith("ritual layer decided:"):
                d["ritual_layer"] = part.split(":", 1)[1].strip()
        verdict = next((p for p in parts if p.lower() in ACCEPTING | REJECTING), None)
        if d.get("item") and d.get("candidate") and verdict:
            d["verdict"] = verdict.lower()
            out.append(d)
    return out


def main(stamp):
    preds = []
    p = Path("predictions.jsonl")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    preds.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    done = set()
    sp = Path("scores.jsonl")
    if sp.exists():
        for line in sp.read_text().splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line).get("prediction_id"))
                except json.JSONDecodeError:
                    pass

    decs = decisions()
    new = 0
    for pred in preds:
        pid = pred.get("id")
        if not pid or pid in done:
            continue
        match = next((d for d in decs
                      if norm(d["item"]) == norm(pred.get("item"))
                      and norm(d["candidate"]) == norm(pred.get("candidate"))), None)
        if not match:
            continue
        actual = "accept" if match["verdict"] in ACCEPTING else "reject"
        predicted = "accept" if str(pred.get("predict", "")).lower() in ACCEPTING else "reject"
        outcome = "hit" if actual == predicted else "miss"
        with sp.open("a") as f:
            f.write(json.dumps({
                "scored_at": stamp, "prediction_id": pid, "item": pred.get("item"),
                "candidate": pred.get("candidate"), "predicted": predicted,
                "actual": actual, "outcome": outcome,
                "confidence": pred.get("confidence"),
                # The scout names a layer when it predicts; the judge names one when
                # it decides, and the two often differ. Keeping only the scout's
                # would file every result under a layer that did not settle it.
                "scout_layer": str(pred.get("deciding_layer", "?")),
                "judge_layer": str(match.get("deciding_layer", "?")),
                "layers_agree": str(pred.get("deciding_layer", "?")) == str(match.get("deciding_layer", "?")),
                "deciding_layer": str(match.get("deciding_layer", pred.get("deciding_layer", "?"))),
                "person_reason": match.get("reason", ""),
            }, ensure_ascii=False) + "\n")
        new += 1
        agree = str(pred.get("deciding_layer", "?")) == str(match.get("deciding_layer", "?"))
        print(f"SCORED {pid} {pred.get('candidate')}: predicted {predicted}, actual {actual} "
              f"-> {outcome}; layer scout {pred.get('deciding_layer','?')} vs judge "
              f"{match.get('deciding_layer','?')}{'' if agree else '  DISAGREE'}")
    print(f"SCORE: {new} prediction(s) closed this run")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

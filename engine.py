#!/usr/bin/env python3
"""Replay notarised evidence; scores are computed views, never stored truth.

Late flags replace the transaction's clean credit retroactively. Fabrication is
applied once at the first outcome/flag position, so a late discovery cannot leave
undeserved clean credit or change the treatment of later clean transactions.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from notary import read_entries, validate_payload


def load_config():
    return json.loads(Path(__file__).with_name("config.json").read_text())


def compute(entries, config):
    entries = list(entries)
    sellers = {seller: {"character": float(config["character_initial"]), "professional": {},
                        "entry_count": 0, "offences": 0} for seller in config["sellers"]}
    grouped = {}
    for index, entry in enumerate(entries):
        if entry.get("kind") == "choice":
            continue
        try:
            validate_payload(entry.get("kind"), entry)
            timestamp = datetime.fromisoformat(entry["notarised_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        grouped.setdefault(entry["task_run_id"], []).append((index, entry))
    events = []
    brier = {}
    for group in grouped.values():
        identities = {(r["seller"], r["buyer"], r["domain"]) for _, r in group}
        if len(identities) != 1:
            continue
        commits = [(i, r) for i, r in group if r["kind"] == "commit"]
        stakes = [(i, r) for i, r in group if r["kind"] == "stake"]
        outcomes = [(i, r) for i, r in group if r["kind"] == "outcome"]
        flags = [(i, r) for i, r in group if r["kind"] == "flag"]
        if len(commits) != 1 or len(stakes) != 1 or len(outcomes) > 1:
            continue
        ci, commit = commits[0]
        si, stake = stakes[0]
        resolutions = outcomes + flags
        if not resolutions:
            continue
        ri = min(i for i, _ in resolutions)
        if ci >= ri or si >= ri:
            continue
        committed_at = datetime.fromisoformat(commit["notarised_at"].replace("Z", "+00:00"))
        if any(datetime.fromisoformat(r["notarised_at"].replace("Z", "+00:00")) <= committed_at for _, r in resolutions):
            continue
        seller, _, domain = next(iter(identities))
        sellers.setdefault(seller, {"character": float(config["character_initial"]), "professional": {},
                                    "entry_count": 0, "offences": 0})
        events.append((ri, seller, bool(flags)))
        sellers[seller]["entry_count"] += 1
        if outcomes:
            actual = 1 if outcomes[0][1]["result"] == "pass" else 0
            weight = stake["stake"]["amount"]
            bucket = brier.setdefault((seller, domain), [0., 0.])
            bucket[0] += weight * (commit["confidence"] - actual) ** 2
            bucket[1] += weight
    for _, seller, fraud in sorted(events):
        record = sellers[seller]
        if fraud:
            record["offences"] += 1
            record["character"] *= config["drop_factor"] ** record["offences"]
        else:
            record["character"] += config["step"] * (1 - record["character"] / 100) / (1 + config["k"] * record["offences"])
    for (seller, domain), (error, weight) in brier.items():
        sellers[seller]["professional"][domain] = 100 * (1 - error / weight)
    return sellers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["lookup"])
    parser.add_argument("domain")
    args = parser.parse_args()
    try:
        config = load_config()
        scores = compute(read_entries(), config)
        for score in scores.values():
            score["professional"] = {args.domain: score["professional"].get(args.domain, config["professional_initial"])}
        print(json.dumps(scores, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f"ENGINE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

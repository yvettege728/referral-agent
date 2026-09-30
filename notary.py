#!/usr/bin/env python3
"""Sole writer of records/entries.jsonl; local demo, not an OS security boundary.

Required payload fields:
  commit:   task_run_id seller buyer domain claim confidence
  stake:    task_run_id seller buyer domain stake:{kind,amount,proof}
  delivery: task_run_id seller buyer domain path summary
  outcome:  task_run_id seller buyer domain result:(pass|fail) note evidence
  flag:     task_run_id seller buyer domain type:fabrication reason
  choice:   task_run_id buyer reason and either seller or action:ask_human; optional referral, confidence
Choice domain is optional. Stake is local effort evidence, not money escrow.
All caller timestamps are discarded recursively. Only the notary stamps time.
Flag writes require NOTARY_CALLER=auditor (an orchestration convention).
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parent
KINDS = {"commit", "stake", "delivery", "outcome", "flag", "choice"}
TIMESTAMP_KEYS = {"time", "date", "timestamp", "timestamps", "ts", "notarised_at", "notarized_at",
                  "createdat", "updatedat", "committedat", "deliveredat", "resolvedat", "reportedat", "notarisedat", "notarizedat"}


def records_path(records_dir=None):
    return Path(records_dir or os.environ.get("SR_RECORDS_DIR") or ROOT / "records")


def canonical_hash(entry):
    data = {k: v for k, v in entry.items() if k != "sha256"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _parse_lines(text):
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank ledger line {number}")
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or record.get("sha256") != canonical_hash(record):
                raise ValueError("invalid record hash")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid ledger line {number}: {exc}") from exc
        entries.append(record)
    if text and not text.endswith("\n"):
        raise ValueError("ledger has an incomplete final line")
    return entries


def read_entries(records_dir=None):
    path = records_path(records_dir) / "entries.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        return _parse_lines(handle.read())


def _strip_timestamps(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lower = key.lower()
            if (lower in TIMESTAMP_KEYS or lower.endswith(("_at", "_time", "_timestamp", "_date"))
                    or key.endswith(("At", "Time", "Timestamp", "Date"))):
                print(f"warning: discarded caller timestamp {key}", file=sys.stderr)
            else:
                result[key] = _strip_timestamps(item)
        return result
    if isinstance(value, list):
        return [_strip_timestamps(item) for item in value]
    return value


def _text(payload, name):
    if not isinstance(payload.get(name), str) or not payload[name].strip():
        raise ValueError(f"{name} must be a nonempty string")


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_payload(kind, payload):
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    for name in ("task_run_id", "buyer"):
        _text(payload, name)
    if kind == "choice":
        _text(payload, "reason")
        if payload.get("action") == "ask_human":
            if payload.get("seller"):
                raise ValueError("ask_human choice cannot select a seller")
        else:
            if "action" in payload:
                raise ValueError("unknown choice action")
            _text(payload, "seller")
        if "domain" in payload:
            _text(payload, "domain")
        return
    for name in ("seller", "domain"):
        _text(payload, name)
    if kind == "commit":
        _text(payload, "claim")
        confidence = payload.get("confidence")
        if not _number(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be finite and between 0 and 1")
    elif kind == "stake":
        stake = payload.get("stake")
        if not isinstance(stake, dict):
            raise ValueError("stake must be an object")
        _text(stake, "kind")
        _text(stake, "proof")
        if not _number(stake.get("amount")) or stake["amount"] <= 0:
            raise ValueError("stake amount must be positive and finite")
    elif kind == "delivery":
        _text(payload, "path")
        _text(payload, "summary")
    elif kind == "outcome":
        if payload.get("result") not in ("pass", "fail"):
            raise ValueError("result must be pass or fail")
        _text(payload, "note")
        _text(payload, "evidence")
    elif kind == "flag":
        if payload.get("type") != "fabrication":
            raise ValueError("flag type must be fabrication")
        _text(payload, "reason")


def append(kind, payload, records_dir=None):
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    payload = _strip_timestamps(payload)
    for reserved in ("entry_id", "sha256", "kind"):
        payload.pop(reserved, None)
    validate_payload(kind, payload)
    if kind == "flag" and os.environ.get("NOTARY_CALLER") != "auditor":
        raise ValueError("only the auditor can append integrity flags")
    directory = records_path(records_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "entries.jsonl").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        entries = _parse_lines(handle.read())
        transaction = [r for r in entries if r.get("task_run_id") == payload["task_run_id"] and r.get("kind") != "choice"]
        if kind != "choice":
            for previous in transaction:
                if any(previous.get(key) != payload[key] for key in ("seller", "buyer", "domain")):
                    raise ValueError("transaction seller/buyer/domain identity mismatch")
            if kind in ("commit", "stake", "outcome") and any(r["kind"] == kind for r in transaction):
                raise ValueError(f"duplicate {kind} for transaction")
        now = datetime.now(timezone.utc)
        if kind == "outcome":
            commitments = [r for r in transaction if r["kind"] == "commit"]
            stakes = [r for r in transaction if r["kind"] == "stake"]
            if not commitments or not stakes:
                raise ValueError("outcome requires a prior commit and stake")
            committed = datetime.fromisoformat(commitments[0]["notarised_at"].replace("Z", "+00:00"))
            if committed >= now:
                raise ValueError("commit must be strictly earlier than outcome")
        record = {**payload, "kind": kind, "entry_id": str(uuid.uuid4()),
                  "notarised_at": now.isoformat(timespec="microseconds").replace("+00:00", "Z")}
        record["sha256"] = canonical_hash(record)
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(KINDS))
    parser.add_argument("payload", help="JSON object")
    args = parser.parse_args()
    try:
        print(json.dumps(append(args.kind, json.loads(args.payload)), ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f"NOTARY ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

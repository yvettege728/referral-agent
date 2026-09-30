#!/usr/bin/env python3
"""Custody audit outside agent turns; integrity flags go through notary only.

before SNAPSHOT stores exact file hashes and the existing ledger byte prefix.
after SNAPSHOT requires identical custody; verify SNAPSHOT permits ledger append
but still requires the original prefix and all other files to remain unchanged.
delivery TASK SELLER BUYER DOMAIN ABSOLUTE_PATH checks that a nonempty file exists.
Snapshots must be outside records. CLI ends with AUDIT PASS or AUDIT FAIL: reason.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from notary import read_entries, records_path


def custody(records_dir=None):
    directory = records_path(records_dir)
    if not directory.exists():
        return {}
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink inside records: {path}")
        if path.is_file():
            hashes[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _snapshot_path(snapshot_path, records_dir):
    snapshot = Path(snapshot_path).resolve()
    if snapshot.is_relative_to(records_path(records_dir).resolve()):
        raise ValueError("custody snapshot must be outside records")
    return snapshot


def before(snapshot_path, records_dir=None):
    snapshot = _snapshot_path(snapshot_path, records_dir)
    read_entries(records_dir)
    ledger = records_path(records_dir) / "entries.jsonl"
    data = {"records_dir": str(records_path(records_dir).resolve()), "files": custody(records_dir),
            "entries_prefix_b64": base64.b64encode(ledger.read_bytes() if ledger.exists() else b"").decode("ascii")}
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def verify(snapshot_path, records_dir=None, allow_append=True):
    snapshot = _snapshot_path(snapshot_path, records_dir)
    previous = json.loads(snapshot.read_text(encoding="utf-8"))
    if previous["records_dir"] != str(records_path(records_dir).resolve()):
        raise ValueError("snapshot belongs to a different records directory")
    read_entries(records_dir)
    current = custody(records_dir)
    old = previous["files"]
    if allow_append:
        if {k: v for k, v in old.items() if k != "entries.jsonl"} != {k: v for k, v in current.items() if k != "entries.jsonl"}:
            raise ValueError("custody files added, deleted, or changed outside ledger")
        if "entries.jsonl" in old and "entries.jsonl" not in current:
            raise ValueError("ledger deleted")
        path = records_path(records_dir) / "entries.jsonl"
        ledger = path.read_bytes() if path.exists() else b""
        prefix = base64.b64decode(previous["entries_prefix_b64"], validate=True)
        if not ledger.startswith(prefix):
            raise ValueError("ledger byte prefix changed or truncated")
    elif old != current:
        raise ValueError("custody files added, deleted, or changed during agent turn")
    return True


def after(snapshot_path, records_dir=None):
    return verify(snapshot_path, records_dir, allow_append=False)


def delivery(task_run_id, seller, buyer, domain, absolute_path, records_dir=None):
    path = Path(absolute_path)
    if not path.is_absolute():
        raise ValueError("delivery path must be absolute")
    if path.is_file() and path.stat().st_size > 0:
        return True
    reason = f"claimed delivery is missing or empty: {path}"
    payload = dict(task_run_id=task_run_id, seller=seller, buyer=buyer, domain=domain,
                   type="fabrication", reason=reason)
    referral = os.environ.get("SR_REFERRAL")
    if referral:
        payload["referral"] = referral
    handoff_sha256 = os.environ.get("SR_HANDOFF_SHA256")
    if handoff_sha256:
        payload["handoff_sha256"] = handoff_sha256
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("notary.py")), "flag", json.dumps(payload)],
                            env={**os.environ, "NOTARY_CALLER": "auditor", "SR_RECORDS_DIR": str(records_path(records_dir))},
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"could not notarise delivery integrity flag: {result.stderr.strip()}")
    raise ValueError(f"fabrication flag notarised; {reason}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for action in ("before", "after", "verify"):
        commands.add_parser(action).add_argument("snapshot_path")
    delivery_parser = commands.add_parser("delivery")
    for field in ("task_run_id", "seller", "buyer", "domain", "absolute_path"):
        delivery_parser.add_argument(field)
    args = parser.parse_args()
    try:
        if args.command == "delivery":
            delivery(args.task_run_id, args.seller, args.buyer, args.domain, args.absolute_path)
        else:
            globals()[args.command](args.snapshot_path)
        print("AUDIT PASS")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"AUDIT FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

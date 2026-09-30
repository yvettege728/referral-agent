"""Contract tests for the notary, deterministic scoring, and custody auditor."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def core():
    def load():
        for name in ("notary", "engine", "audit"):
            assert importlib.util.find_spec(name), f"Missing core module: {name}"
            yield importlib.import_module(name)
    return load()


def tx(i="one", seller="seller-a", domain="math"):
    return dict(task_run_id=i, seller=seller, buyer="buyer", domain=domain)


def commit(n, folder, i="one", confidence=.8, seller="seller-a", domain="math"):
    common = tx(i, seller, domain)
    n.append("commit", {**common, "claim": "deliver", "confidence": confidence}, folder)
    n.append("stake", {**common, "stake": {"kind": "compute", "amount": 1, "proof": "mock-local-work"}}, folder)
    return common


def outcome(n, folder, common, result="pass"):
    return n.append("outcome", {**common, "result": result, "note": "checker", "evidence": "check.py"}, folder)


def config():
    return json.loads((ROOT / "config.json").read_text())


def test_stamps_and_discards_timestamps_recursively(core, tmp_path, capsys):
    n, _, _ = core
    record = n.append("commit", {**tx(), "claim": "deliver", "confidence": .5,
        "timestamp": "fake", "notarised_at": "fake", "metadata": {"created_at": "fake", "committedAt": "fake", "reportedAt": "fake", "eventTime": "fake", "nested": [{"time": "fake"}]},
        "entry_id": "fake", "sha256": "fake"}, tmp_path)
    assert record["entry_id"] != "fake"
    assert record["notarised_at"].endswith("Z")
    assert "timestamp" not in record
    assert record["metadata"] == {"nested": [{}]}
    assert record["sha256"] == n.canonical_hash(record)
    assert "timestamp" in capsys.readouterr().err.lower()
    assert n.read_entries(tmp_path) == [record]


@pytest.mark.parametrize("value", [-.1, 1.1, float("nan"), float("inf"), True, "0.5"])
def test_confidence_rejected(core, tmp_path, value):
    n, _, _ = core
    with pytest.raises(ValueError):
        n.append("commit", {**tx(), "claim": "claim", "confidence": value}, tmp_path)


def test_outcome_requires_commit_stake_and_matching_identity(core, tmp_path):
    n, _, _ = core
    with pytest.raises(ValueError):
        outcome(n, tmp_path, tx())
    n.append("commit", {**tx(), "claim": "claim", "confidence": .8}, tmp_path)
    with pytest.raises(ValueError):
        outcome(n, tmp_path, tx())
    with pytest.raises(ValueError):
        n.append("stake", {**tx(), "buyer": "intruder", "stake": {"kind": "compute", "amount": 1, "proof": "work"}}, tmp_path)
    n.append("stake", {**tx(), "stake": {"kind": "compute", "amount": 1, "proof": "work"}}, tmp_path)
    result = outcome(n, tmp_path, tx())
    assert result["notarised_at"] > n.read_entries(tmp_path)[0]["notarised_at"]
    with pytest.raises(ValueError):
        outcome(n, tmp_path, tx())
    with pytest.raises(ValueError):
        n.append("commit", {**tx(), "claim": "again", "confidence": .5}, tmp_path)
    with pytest.raises(ValueError):
        n.append("stake", {**tx(), "stake": {"kind": "compute", "amount": 1, "proof": "work"}}, tmp_path)


@pytest.mark.parametrize("amount,proof", [(0,"x"),(-1,"x"),(float("inf"),"x"),(True,"x"),(1,"")])
def test_invalid_stake(core, tmp_path, amount, proof):
    n, _, _ = core
    with pytest.raises(ValueError):
        n.append("stake", {**tx(), "stake": {"kind": "compute", "amount": amount, "proof": proof}}, tmp_path)


def test_flag_restricted_and_choice_escalation(core, tmp_path, monkeypatch):
    n, _, _ = core
    common = commit(n, tmp_path)
    flag = {**common, "type": "fabrication", "reason": "missing"}
    monkeypatch.delenv("NOTARY_CALLER", raising=False)
    with pytest.raises(ValueError):
        n.append("flag", flag, tmp_path)
    monkeypatch.setenv("NOTARY_CALLER", "auditor")
    n.append("flag", flag, tmp_path)
    r = n.append("choice", {"task_run_id": "next", "buyer": "buyer", "action": "ask_human", "reason": "too risky"}, tmp_path)
    assert r["action"] == "ask_human"


def test_calibration_honest_failure_and_repeat_offences(core, tmp_path, monkeypatch):
    n, e, _ = core
    monkeypatch.setenv("NOTARY_CALLER", "auditor")
    for i in range(10):
        outcome(n, tmp_path, commit(n, tmp_path, str(i)))
    assert e.compute(n.read_entries(tmp_path), config())["seller-a"]["character"] == pytest.approx(90, abs=5)
    first = commit(n, tmp_path, "fraud1")
    n.append("flag", {**first, "type": "fabrication", "reason": "missing"}, tmp_path)
    outcome(n, tmp_path, first, "fail")
    assert e.compute(n.read_entries(tmp_path), config())["seller-a"]["character"] == pytest.approx(30, abs=5)
    for i in range(20):
        outcome(n, tmp_path, commit(n, tmp_path, f"recover{i}"), "fail")
    recovered = e.compute(n.read_entries(tmp_path), config())["seller-a"]
    assert recovered["character"] == pytest.approx(70, abs=4)
    second = commit(n, tmp_path, "fraud2")
    n.append("flag", {**second, "type": "fabrication", "reason": "missing"}, tmp_path)
    n.append("flag", {**second, "type": "fabrication", "reason": "still missing"}, tmp_path)
    outcome(n, tmp_path, second, "fail")
    final = e.compute(n.read_entries(tmp_path), config())["seller-a"]
    assert final["character"] == pytest.approx(10, abs=5)
    assert final["offences"] == 2
    assert final["entry_count"] == 32


def test_weighted_domains_cold_start_and_unproved_ignored(core, tmp_path):
    n, e, _ = core
    common = commit(n, tmp_path, confidence=.8)
    outcome(n, tmp_path, common)
    other = tx("two")
    n.append("commit", {**other, "claim": "deliver", "confidence": .6}, tmp_path)
    n.append("stake", {**other, "stake": {"kind": "compute", "amount": 3, "proof": "work"}}, tmp_path)
    outcome(n, tmp_path, other, "fail")
    outcome(n, tmp_path, commit(n, tmp_path, "recipe", confidence=.5, domain="recipe"))
    entries = n.read_entries(tmp_path)
    scores = e.compute(entries, config())
    assert scores["seller-a"]["professional"]["math"] == pytest.approx(72)
    assert scores["seller-a"]["professional"]["recipe"] == pytest.approx(75)
    assert scores["seller-b"]["character"] == 40
    assert scores["seller-b"]["entry_count"] == 0
    assert e.compute([r for r in entries if r["kind"] != "stake"], config())["seller-a"]["entry_count"] == 0


def test_late_flag_replays_at_resolution_without_clean_credit(core, tmp_path, monkeypatch):
    n, e, _ = core
    monkeypatch.setenv("NOTARY_CALLER", "auditor")
    first = commit(n, tmp_path, "fraud")
    outcome(n, tmp_path, first)
    outcome(n, tmp_path, commit(n, tmp_path, "clean"))
    flag = n.append("flag", {**first, "type": "fabrication", "reason": "late discovery"}, tmp_path)
    late = n.read_entries(tmp_path)
    earlier = late[:-1]
    earlier.insert(2, flag)
    assert e.compute(late, config()) == e.compute(earlier, config())


def cli(script, *args, records):
    return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
        env={**os.environ, "SR_RECORDS_DIR": str(records)}, text=True, capture_output=True)


def test_audit_detects_rehashed_middle_edit_and_append_permissions(core, tmp_path):
    n, _, _ = core
    records = tmp_path / "records"
    common = commit(n, records)
    snapshot = tmp_path / "snapshot.json"
    assert cli("audit.py", "before", snapshot, records=records).returncode == 0
    outcome(n, records, common)
    assert cli("audit.py", "verify", snapshot, records=records).returncode == 0
    assert cli("audit.py", "after", snapshot, records=records).returncode == 1
    entries = n.read_entries(records)
    entries[0]["claim"] = "changed"
    entries[0]["sha256"] = n.canonical_hash(entries[0])
    (records / "entries.jsonl").write_text("".join(json.dumps(r) + "\n" for r in entries))
    result = cli("audit.py", "verify", snapshot, records=records)
    assert result.returncode == 1
    assert "AUDIT FAIL" in result.stdout


@pytest.mark.parametrize("operation", ["add", "delete"])
def test_custody_detects_file_set_changes(core, tmp_path, operation):
    records = tmp_path / "records"
    records.mkdir()
    extra = records / "extra.txt"
    extra.write_text("kept")
    snapshot = tmp_path / "snapshot.json"
    assert cli("audit.py", "before", snapshot, records=records).returncode == 0
    if operation == "add":
        (records / "new.txt").write_text("new")
    else:
        extra.unlink()
    assert cli("audit.py", "after", snapshot, records=records).returncode == 1


def test_delivery_audit_flags_only_missing_or_empty(core, tmp_path):
    n, _, _ = core
    records = tmp_path / "records"
    commit(n, records)
    target = tmp_path / "output.json"
    result = cli("audit.py", "delivery", "one", "seller-a", "buyer", "math", target, records=records)
    assert result.returncode == 1
    assert "fabrication flag notarised" in result.stdout.lower()
    assert n.read_entries(records)[-1]["kind"] == "flag"
    target.write_text("{}")
    assert cli("audit.py", "delivery", "one", "seller-a", "buyer", "math", target, records=records).returncode == 0


def test_delivery_does_not_claim_notarised_flag_when_notary_rejects(core, tmp_path):
    n, _, _ = core
    records = tmp_path / "records"
    commit(n, records)
    result = cli("audit.py", "delivery", "one", "seller-a", "wrong-buyer", "math", tmp_path / "missing.json", records=records)
    assert result.returncode == 1
    assert "fabrication" not in result.stdout.lower()
    assert all(r["kind"] != "flag" for r in n.read_entries(records))


def test_lookup_cli_and_notary_cli(core, tmp_path):
    result = cli("notary.py", "choice", json.dumps({**tx(), "reason": "test"}), records=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["kind"] == "choice"
    result = cli("engine.py", "lookup", "math", records=tmp_path)
    scores = json.loads(result.stdout)
    assert set(scores) == {"seller-a", "seller-b", "seller-c"}
    assert scores["seller-a"]["professional"]["math"] == 50


def test_notary_rejects_outcome_after_future_dated_commit(core, tmp_path):
    n, _, _ = core
    commit(n, tmp_path)
    records = n.read_entries(tmp_path)
    records[0]["notarised_at"] = "2999-01-01T00:00:00.000000Z"
    records[0]["sha256"] = n.canonical_hash(records[0])
    (tmp_path / "entries.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    with pytest.raises(ValueError, match="strictly earlier"):
        outcome(n, tmp_path, tx())


@pytest.mark.parametrize("broken", ["no_commit", "no_stake", "no_proof", "same_time", "identity"])
def test_unproved_or_invalid_fraud_has_no_score_effect(core, tmp_path, monkeypatch, broken):
    n, e, _ = core
    monkeypatch.setenv("NOTARY_CALLER", "auditor")
    common = commit(n, tmp_path)
    n.append("flag", {**common, "type": "fabrication", "reason": "missing"}, tmp_path)
    entries = n.read_entries(tmp_path)
    if broken == "no_commit":
        entries = [r for r in entries if r["kind"] != "commit"]
    elif broken == "no_stake":
        entries = [r for r in entries if r["kind"] != "stake"]
    elif broken == "no_proof":
        entries[1]["stake"]["proof"] = ""
    elif broken == "same_time":
        entries[2]["notarised_at"] = entries[0]["notarised_at"]
    else:
        entries[2]["buyer"] = "intruder"
    score = e.compute(entries, config())["seller-a"]
    assert score["character"] == 40
    assert score["offences"] == 0
    assert score["entry_count"] == 0


def test_concurrent_notary_writes_are_complete_and_unique(core, tmp_path):
    n, _, _ = core
    processes = []
    for i in range(16):
        payload = {**tx(str(i)), "claim": "deliver", "confidence": .5}
        processes.append(subprocess.Popen([sys.executable, str(ROOT / "notary.py"), "commit", json.dumps(payload)],
            env={**os.environ, "SR_RECORDS_DIR": str(tmp_path)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    for process in processes:
        _, error = process.communicate(timeout=20)
        assert process.returncode == 0, error
    records = n.read_entries(tmp_path)
    assert len(records) == 16
    assert len({r["entry_id"] for r in records}) == 16


def test_empty_custody_and_hash_corruption(core, tmp_path):
    n, _, _ = core
    records = tmp_path / "nonexistent"
    snapshot = tmp_path / "snapshot.json"
    assert cli("audit.py", "before", snapshot, records=records).returncode == 0
    assert cli("audit.py", "after", snapshot, records=records).returncode == 0
    commit(n, records)
    assert cli("audit.py", "verify", snapshot, records=records).returncode == 0
    ledger = records / "entries.jsonl"
    ledger.write_text(ledger.read_text().replace('"claim": "deliver"', '"claim": "edited"'))
    assert cli("audit.py", "verify", snapshot, records=records).returncode == 1
    assert cli("audit.py", "before", tmp_path / "new.json", records=records).returncode == 1


def test_snapshot_inside_records_is_rejected(core, tmp_path):
    result = cli("audit.py", "before", tmp_path / "snapshot.json", records=tmp_path)
    assert result.returncode == 1
    assert "outside records" in result.stdout


def test_engine_ignores_naive_timestamps(core, tmp_path):
    n, e, _ = core
    outcome(n, tmp_path, commit(n, tmp_path))
    entries = n.read_entries(tmp_path)
    entries[0]["notarised_at"] = "2026-01-01T00:00:00"
    assert e.compute(entries, config())["seller-a"]["entry_count"] == 0


def test_default_calibration_parameters_are_fitted():
    defaults = config()
    step = 100 * (1 - (1 / 6) ** .1)
    k = (step / 100) / (1 - (3 / 7) ** (1 / 20)) - 1
    assert defaults["step"] == pytest.approx(step, abs=1e-12)
    assert defaults["k"] == pytest.approx(k, abs=1e-12)


@pytest.mark.parametrize("kind", ["commit", "stake"])
def test_oversized_integer_is_rejected_without_traceback(core, tmp_path, kind):
    n, e, _ = core
    payload = ({**tx(), "claim": "deliver", "confidence": 10 ** 400} if kind == "commit"
               else {**tx(), "stake": {"kind": "compute", "amount": 10 ** 400, "proof": "work"}})
    with pytest.raises(ValueError, match="finite"):
        n.append(kind, payload, tmp_path)
    result = cli("notary.py", kind, json.dumps(payload), records=tmp_path)
    assert result.returncode == 1
    assert "NOTARY ERROR" in result.stderr
    assert "finite" in result.stderr
    assert "Traceback" not in result.stderr
    outcome(n, tmp_path, commit(n, tmp_path))
    entries = n.read_entries(tmp_path)
    for entry in entries:
        if entry["kind"] == kind:
            entry.update(payload)
    assert e.compute(entries, config())["seller-a"]["entry_count"] == 0

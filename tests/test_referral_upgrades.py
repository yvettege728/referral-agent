import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_referral_reliability_aggregates_completed_transactions():
    from referral import referral_reliability
    entries = [
        {'kind': 'choice', 'task_run_id': 't1', 'referral': 'referral-agent-1', 'seller': 'seller-a', 'confidence': .8},
        {'kind': 'outcome', 'task_run_id': 't1', 'referral': 'referral-agent-1', 'result': 'pass'},
        {'kind': 'choice', 'task_run_id': 't2', 'referral': 'referral-agent-1', 'seller': 'seller-a', 'confidence': .8},
        {'kind': 'outcome', 'task_run_id': 't2', 'referral': 'referral-agent-1', 'result': 'fail'},
        {'kind': 'choice', 'task_run_id': 'incomplete', 'referral': 'referral-agent-1', 'seller': 'seller-a', 'confidence': .2},
    ]
    result = referral_reliability(entries, 'referral-agent-1')
    assert result == {'recommendations': 3, 'completed': 2, 'successes': 1, 'reliability': 66.0}


def test_handoff_digest_is_stable_and_sensitive_to_translated_brief():
    from referral import handoff_digest
    assert handoff_digest('task\n') == handoff_digest('task\n')
    assert handoff_digest('task\n') != handoff_digest('task changed\n')


def test_mediated_run_records_handoff_hash_and_history_metric(tmp_path):
    label = 'upgrade-' + tmp_path.name + '-' + str(time.time_ns())
    env = {**os.environ, 'PYTHON': sys.executable, 'SR_RECORDS_DIR': str(tmp_path / 'records')}
    result = __import__('subprocess').run(
        ['bash', str(ROOT / 'run.sh'), '01', label, '--mock', '--mediated'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    seller_inputs = sorted((ROOT / 'runs' / label).glob('*-seller-*.input.json'))
    assert seller_inputs
    seller_input = json.loads(seller_inputs[0].read_text())
    assert len(seller_input['handoff_sha256']) == 64
    records = [json.loads(line) for line in (tmp_path / 'records' / 'entries.jsonl').read_text().splitlines()]
    delivery = next(entry for entry in records if entry['kind'] == 'delivery')
    assert delivery['handoff_sha256'] == seller_input['handoff_sha256']
    flag = next(entry for entry in records if entry['kind'] == 'flag')
    assert flag['handoff_sha256'] == seller_input['handoff_sha256']
    metrics = json.loads((ROOT / 'runs' / label / 'metrics.json').read_text())
    assert metrics['referral_reliability']['completed'] == 2

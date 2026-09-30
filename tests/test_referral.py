import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_referral_recommends_with_explicit_confidence():
    import referral
    scores = {
        'seller-a': {'character': 70, 'professional': {'research': 80}},
        'seller-b': {'character': 85, 'professional': {'research': 60}},
    }
    result = referral.recommend(['seller-a', 'seller-b'], scores, 'research')
    assert result == {'seller': 'seller-b', 'confidence': 0.85,
                      'reason': 'Highest character, then professional score in this domain.'}


def test_referral_confidence_is_scored_against_final_outcome():
    import referral
    assert referral.score_recommendation(.8, 'pass') == pytest.approx(96)
    assert referral.score_recommendation(.8, 'fail') == pytest.approx(36)


def test_mediated_brief_excludes_private_buyer_context():
    import referral
    brief = referral.mediated_brief('TASK: audit suppliers\nPRIVATE: budget is $10,000\nFORMAT: CSV')
    assert 'PRIVATE:' not in brief
    assert 'audit suppliers' in brief
    assert 'FORMAT: CSV' in brief


def test_mediated_run_has_referral_records_and_no_direct_buyer_context(tmp_path):
    env = {'PYTHON': sys.executable, 'SR_RECORDS_DIR': str(tmp_path / 'records')}
    label = 'mediated-test-' + tmp_path.name + '-' + str(time.time_ns())
    result = subprocess.run(['bash', str(ROOT / 'run.sh'), '01', label, '--mock', '--mediated'],
                            cwd=ROOT, env={**__import__('os').environ, **env},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    records = [json.loads(line) for line in (tmp_path / 'records' / 'entries.jsonl').read_text().splitlines()]
    assert any(entry.get('kind') == 'choice' and entry.get('referral') == 'referral-agent-1' for entry in records)
    assert any(entry.get('kind') == 'flag' and entry.get('referral') == 'referral-agent-1' for entry in records)
    seller_inputs = sorted((ROOT / 'runs' / label).glob('*-seller-*.input.json'))
    assert seller_inputs
    seller_context = json.loads(seller_inputs[0].read_text())
    assert 'buyer_private_context' not in seller_context
    assert seller_context['channel'] == 'referral'

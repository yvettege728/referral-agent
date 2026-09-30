import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_internal_team_produces_distinct_role_opinions_and_lead_dissent():
    from team import run_team

    result = run_team({
        'available': ['seller-a', 'seller-b', 'seller-c'],
        'domain': 'writing',
        'mode': 'improved',
        'lookup': {
            'seller-a': {'character': 88, 'professional': {'writing': 78}},
            'seller-b': {'character': 72, 'professional': {'writing': 91}},
            'seller-c': {'character': 65, 'professional': {'writing': 96}},
        },
        'brief': 'Write a careful report.',
        'high_stake': False,
        'human_threshold': 60,
    })

    assert [opinion['role'] for opinion in result['opinions']] == [
        'buyer_liaison', 'talent_scout', 'research_analyst', 'risk_partner'
    ]
    assert len({opinion['seller'] for opinion in result['opinions'] if opinion['seller']}) >= 2
    assert result['lead']['seller'] in {'seller-a', 'seller-b', 'seller-c'}
    assert result['lead']['dissent']
    assert result['lead']['decision_factors']
    assert result['lead']['confidence_calculation']['dissent_penalty'] > 0
    assert result['lead']['confidence_calculation']['final'] == result['lead']['confidence']
    assert all('rationale' in opinion and 0 <= opinion['confidence'] <= 1 for opinion in result['opinions'])


def test_lead_selection_responds_to_role_weights():
    from team import run_team

    context = {
        'available': ['seller-a', 'seller-b', 'seller-c'],
        'domain': 'writing',
        'mode': 'improved',
        'lookup': {
            'seller-a': {'character': 88, 'professional': {'writing': 78}},
            'seller-b': {'character': 72, 'professional': {'writing': 91}},
            'seller-c': {'character': 65, 'professional': {'writing': 96}},
        },
    }
    risk_led = run_team(context)
    speed_led = run_team({**context, 'role_weights': {
        'buyer_liaison': 0.05, 'talent_scout': 0.80,
        'research_analyst': 0.05, 'risk_partner': 0.10,
    }})

    assert risk_led['lead']['seller'] == 'seller-a'
    assert speed_led['lead']['seller'] == 'seller-c'
    assert speed_led['lead']['decision_factors'][1]['weight'] == 0.80


def test_mediated_run_records_team_debate_and_hides_private_buyer_context(tmp_path):
    label = 'team-' + tmp_path.name + '-' + str(time.time_ns())
    env = {**os.environ, 'PYTHON': sys.executable, 'SR_RECORDS_DIR': str(tmp_path / 'records')}
    result = subprocess.run(
        ['bash', str(ROOT / 'run.sh'), '01', label, '--mock', '--mediated'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

    run_dir = ROOT / 'runs' / label
    debate = json.loads((run_dir / 'team-debate.json').read_text())
    assert len(debate['opinions']) == 4
    assert debate['lead']['dissent']
    assert {opinion['role'] for opinion in debate['opinions']} == {
        'buyer_liaison', 'talent_scout', 'research_analyst', 'risk_partner'
    }
    metrics = json.loads((run_dir / 'metrics.json').read_text())
    assert metrics['team_member_calls'] == 4
    records = [json.loads(line) for line in (tmp_path / 'records' / 'entries.jsonl').read_text().splitlines()]
    choice = next(entry for entry in records if entry.get('kind') == 'choice' and 'seller' in entry)
    assert choice['confidence_calculation']['dissent_penalty'] >= 0
    assert len(choice['decision_factors']) == 4
    referral_choice = json.loads((run_dir / '01-referral-choice.input.json').read_text())
    assert 'PRIVATE:' not in referral_choice['brief']
    seller_inputs = sorted(run_dir.glob('*-seller-*.input.json'))
    assert seller_inputs
    seller_input = json.loads(seller_inputs[0].read_text())
    assert seller_input['channel'] == 'referral'
    assert 'buyer_private_context' not in seller_input


def test_retry_keeps_one_team_trace_per_attempt(tmp_path):
    label = 'team-trace-' + tmp_path.name + '-' + str(time.time_ns())
    env = {**os.environ, 'SR_RECORDS_DIR': str(tmp_path / 'records')}
    result = subprocess.run(
        ['bash', str(ROOT / 'run.sh'), '01', label, '--mock', '--mediated'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = ROOT / 'runs' / label
    traces = sorted(run_dir.glob('team-debate-attempt-*.json'))
    assert len(traces) == 2
    aggregate = json.loads((run_dir / 'team-debate.json').read_text())
    assert len(aggregate['attempts']) == 2
    assert all(len(attempt['opinions']) == 4 for attempt in aggregate['attempts'])


def test_live_mode_streams_execution_milestones(tmp_path):
    label = 'team-live-' + tmp_path.name + '-' + str(time.time_ns())
    env = {**os.environ, 'SR_RECORDS_DIR': str(tmp_path / 'records')}
    result = subprocess.run(
        ['bash', str(ROOT / 'run.sh'), '01', label, '--mock', '--mediated', '--live'],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '[live] referral team completed' in result.stdout
    assert '[live] seller-c delivery' in result.stdout
    assert '[live] audit' in result.stdout
    assert 'status": "pass"' in result.stdout

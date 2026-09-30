import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def project(tmp_path):
    root = tmp_path/'project'
    root.mkdir()
    for path in ROOT.iterdir():
        if path.name in {'.venv', 'runs', 'records', 'reference', '__pycache__', '.pytest_cache', 'tests'}:
            continue
        if path.is_dir():
            shutil.copytree(path, root/path.name)
        else:
            shutil.copy2(path, root/path.name)
    return root


def run(project, task, label, *args, extra=None):
    assert (project/'run.sh').exists(), 'orchestrator must exist'
    env = {**os.environ, 'PYTHON': sys.executable, **(extra or {})}
    result = subprocess.run(['bash',str(project/'run.sh'), task,label,*args], cwd=project, env=env, capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    return json.loads((project/'runs'/label/'metrics.json').read_text())


def test_baseline_caught_and_recovers(project):
    metrics = run(project,'01','baseline','--baseline','--mock')
    assert metrics['bad_deliveries'] == 1
    assert metrics['retries'] == 1
    assert metrics['ask_human'] == 0
    assert metrics['agent_calls'] == 8
    entries = [json.loads(s) for s in (project/'records/entries.jsonl').read_text().splitlines()]
    assert any(e['kind']=='flag' and e['seller']=='seller-c' for e in entries)
    for seller in ('seller-c','seller-b'):
        selected = [e for e in entries if e.get('seller')==seller]
        commit = next(e for e in selected if e['kind']=='commit')
        delivery = next(e for e in selected if e['kind']=='delivery')
        assert commit['notarised_at'] < delivery['notarised_at']
    assert 'fabrication' in (project/'runs/baseline/audit.txt').read_text()


def test_improved_remembers_liar(project):
    first = run(project,'01','first','--mock')
    second = run(project,'01','second','--mock')
    assert first['bad_deliveries'] == 1
    assert second['bad_deliveries'] == 0
    assert (project/'runs/second/audit.txt').read_text().rstrip().endswith('AUDIT PASS')


def test_honest_miss_has_no_flag(project):
    metrics = run(project,'04','honest','--mock',extra={'SR_FORCE_SELLER':'seller-b'})
    assert metrics['bad_deliveries'] >= 1
    records = [json.loads(s) for s in (project/'records/entries.jsonl').read_text().splitlines()]
    assert not any(e['kind']=='flag' and e.get('seller')=='seller-b' for e in records)


def test_high_stake_asks_without_agent_calls(project):
    path = project/'tasks/01/task.json'
    task=json.loads(path.read_text()); task['high_stake']=True
    path.write_text(json.dumps(task))
    metrics=run(project,'01','high','--mock')
    assert metrics['ask_human']==1
    assert metrics['agent_calls']==0


def test_all_candidates_fail_exhausts_retries(project):
    (project/'tasks/01/check.py').write_text('print("FAIL: injected checker failure")\nraise SystemExit(1)\n')
    metrics=run(project,'01','exhaust','--baseline','--mock')
    assert metrics['retries']==2
    assert metrics['ask_human']==1
    assert metrics['bad_deliveries']==3


def test_nonmock_requires_api_key_and_never_falls_back_to_mock(project):
    env={**os.environ,'PYTHON':sys.executable}
    env.pop('OPENAI_API_KEY',None)
    result=subprocess.run(['bash',str(project/'run.sh'),'01','real'],cwd=project,capture_output=True,text=True,env=env)
    assert result.returncode != 0
    assert 'OPENAI_API_KEY' in result.stderr
    assert not (project/'runs/real').exists()


def test_eval_comparison(project):
    assert (project/'eval.sh').exists(), 'evaluation must exist'
    result=subprocess.run(['bash',str(project/'eval.sh'),'--mock'],cwd=project,capture_output=True,text=True,env={**os.environ,'PYTHON':sys.executable},timeout=120)
    assert result.returncode==0, result.stdout+result.stderr
    summary=json.loads((project/'runs/eval-summary.json').read_text())
    assert summary['improved']['bad_deliveries'] < summary['baseline']['bad_deliveries']
    assert len(summary['baseline']['calls_per_task'])==8
    assert len(summary['improved']['calls_per_task'])==8
    assert (project/'runs/baseline-entries.jsonl').exists()
    assert (project/'runs/improved-entries.jsonl').exists()


def test_choice_cannot_override_wrapper_metadata(project):
    path=project/'agents/mock_buyer.py'
    path.write_text(path.read_text().replace("'reason':reason}","'reason':reason,'buyer':'wrong-buyer','task_run_id':'unrelated'}"))
    run(project,'01','metadata','--mock',extra={'SR_FORCE_SELLER':'seller-a'})
    entries=[json.loads(s) for s in (project/'records/entries.jsonl').read_text().splitlines()]
    assert all(e['buyer']=='buyer' and e['task_run_id'].startswith('metadata:') for e in entries)


@pytest.mark.parametrize('baseline',[False,True])
def test_all_low_character_asks(project,baseline):
    path=project/'config.json'
    cfg=json.loads(path.read_text());cfg['character_initial']=30
    path.write_text(json.dumps(cfg))
    args=['--mock']+(['--baseline'] if baseline else [])
    metrics=run(project,'01','low',*args)
    assert metrics['ask_human']==1
    assert metrics['agent_calls']==0


def test_failed_flag_write_stops_run(project):
    path=project/'audit.py'
    path.write_text(path.read_text().replace('delivery(args.task_run_id, args.seller, args.buyer, args.domain, args.absolute_path)', 'raise ValueError("could not notarise delivery integrity flag: injected rejection")'))
    result=subprocess.run(['bash',str(project/'run.sh'),'01','broken-audit','--mock'],cwd=project,capture_output=True,text=True,env={**os.environ,'PYTHON':sys.executable})
    assert result.returncode != 0
    metrics=json.loads((project/'runs/broken-audit/metrics.json').read_text())
    assert metrics['status']=='error'
    entries=[json.loads(s) for s in (project/'records/entries.jsonl').read_text().splitlines()]
    assert not any(e['kind']=='outcome' for e in entries)


def test_huge_commit_is_failed_attempt_and_recovers(project):
    path=project/'agents/mock_seller.py'
    path.write_text(path.read_text().replace("'confidence':confidence", "'confidence':(10**400 if seller == 'seller-c' else confidence)"))
    metrics=run(project,'01','big-number','--baseline','--mock')
    assert metrics['status']=='pass'
    assert metrics['bad_deliveries']==1
    assert metrics['retries']==1
    assert 'confidence' in (project/'runs/big-number/timeline.md').read_text()

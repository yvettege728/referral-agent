#!/usr/bin/env python3
"""Run identical task sequences with isolated record histories and write metrics."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mock',action='store_true')
    parser.add_argument('sequence',nargs=8)
    args=parser.parse_args()
    if not args.mock:
        parser.error('this package implements only --mock; real-agent adapter is a stub')
    runs=ROOT/'runs'
    runs.mkdir(exist_ok=True)
    batch=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive=runs/'_archives'/batch
    archive.mkdir(parents=True)
    totals={}
    env=dict(os.environ)
    for key in ('SR_RECORDS_DIR','NOTARY_CALLER','SR_FORCE_SELLER'):
        env.pop(key,None)
    env['PYTHON']=sys.executable
    # These interventions are shared between arms and visible in every transcript.
    interventions={6:'seller-b',7:'seller-c'}
    for mode in ('baseline','improved'):
        records=ROOT/'records'
        if records.exists():
            shutil.move(str(records),str(archive/(mode+'-prior-records')))
        measurements=[]
        for index,task in enumerate(args.sequence,1):
            label=f'{mode}-{index:02d}'
            previous=runs/label
            if previous.exists():
                shutil.move(str(previous),str(archive/label))
            turn_env={**env}
            if index in interventions:
                turn_env['SR_FORCE_SELLER']=interventions[index]
            command=['bash',str(ROOT/'run.sh'),task,label,'--mock']
            if mode=='baseline':
                command.append('--baseline')
            process=subprocess.run(command,cwd=ROOT,env=turn_env,text=True,capture_output=True)
            if process.returncode:
                print(process.stdout+process.stderr,file=sys.stderr)
                return process.returncode
            metrics=json.loads((runs/label/'metrics.json').read_text())
            measurements.append(metrics)
            print(f'{label}: {metrics["status"]}, bad={metrics["bad_deliveries"]}, calls={metrics["agent_calls"]}',flush=True)
        copy=runs/(mode+'-entries.jsonl')
        if copy.exists():
            shutil.move(str(copy),str(archive/copy.name))
        shutil.copy2(records/'entries.jsonl',copy)
        total={key:sum(m[key] for m in measurements) for key in ('bad_deliveries','retries','ask_human','agent_calls','attempts')}
        total['calls_per_task']=[m['agent_calls'] for m in measurements]
        total['average_calls']=total['agent_calls']/len(measurements)
        total['bad_delivery_rate']=total['bad_deliveries']/total['attempts'] if total['attempts'] else 0
        total['retries_per_task']=total['retries']/len(measurements)
        totals[mode]=total
    for name in ('eval-summary.md','eval-summary.json'):
        path=runs/name
        if path.exists():
            shutil.move(str(path),str(archive/name))
    (runs/'eval-summary.json').write_text(json.dumps(totals,indent=2)+'\n')
    b,i=totals['baseline'],totals['improved']
    lines=['# Mock evaluation','',
           'Both arms start with empty records. Task sequence: '+', '.join(args.sequence)+'.',
           'Task 6 forces seller-b on the hard task; task 7 forces seller-c again. These shared interventions exercise honest misses and repeat fabrication. Other picks follow each buyer policy.',
           'All agent calls are local Python mock processes; no real models were used.',
           'This is a deterministic policy demonstration, not a measured effect on real-model behaviour. Both arms use the same seller script: seller-c always fabricates, seller-b deliberately fails task 04, and seller-a always succeeds. Baseline selects by fixed description order; improved sorts computed reputation. The improvement follows these programmed policies and this task sequence.',
           'Baseline is not entirely reputation-free: baseline also uses reputation for the safety stop when all remaining candidates are below the character threshold; reputation is withheld only from its buyer selection input.',
           'Zero human escalations in this sequence do not prove safety: seller-a remains available and succeeds within the retry budget. Separate tests exercise high-stake tasks, low-character candidates, and retry exhaustion.','',
           '| Metric | Baseline | Improved |','|---|---:|---:|',
           f'| Bad deliveries | {b["bad_deliveries"]} | {i["bad_deliveries"]} |',
           f'| Bad-delivery rate (bad / seller attempts) | {b["bad_delivery_rate"]:.1%} | {i["bad_delivery_rate"]:.1%} |',
           f'| Retries | {b["retries"]} | {i["retries"]} |',
           f'| Retries per task | {b["retries_per_task"]:.3f} | {i["retries_per_task"]:.3f} |',
           f'| Ask-human events | {b["ask_human"]} | {i["ask_human"]} |',
           f'| Agent calls per task (mean) | {b["average_calls"]:.2f} | {i["average_calls"]:.2f} |',
           f'| Agent calls for tasks 1–8 | {", ".join(map(str,b["calls_per_task"]))} | {", ".join(map(str,i["calls_per_task"]))} |','',
           'A normal attempt uses four agent calls: buyer choice, seller commit, seller delivery, buyer outcome. Notary, lookup, checker, and auditor calls are not agent calls.',
           'A bad delivery is a selected seller attempt that fails its checker, receives a fabrication flag, or fails its required transcript contract.','',
           'Runs containing seller-c end with AUDIT FAIL for the detected fabrication even if recovery succeeds; the other runs end with AUDIT PASS. See each timeline.md, audit.txt, and metrics.json.',
           'History snapshots: baseline-entries.jsonl and improved-entries.jsonl. Previous evaluation artifacts and pre-reset records are retained in _archives/.','']
    (runs/'eval-summary.md').write_text('\n'.join(lines))
    if i['bad_deliveries'] >= b['bad_deliveries']:
        print('evaluation failed: improved bad deliveries must be strictly fewer',file=sys.stderr)
        return 1
    print('Evaluation complete: '+str(runs/'eval-summary.md'))
    return 0


if __name__=='__main__':
    sys.exit(main())

"""Reproducible HW2 Extra experiment: poison the reputation lookup tool.

The intended behavior is to recommend seller-a, whose record is clean, rather
than seller-c, whose record contains a fabrication flag. The first run trusts
the lookup response. The second run recomputes the scores from the notarised
records and rejects the poisoned response.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

_configured_repo = os.environ.get('SERVICE_RECORD_REPO')
_candidates = [
    Path(_configured_repo).expanduser() if _configured_repo else None,
    Path(__file__).resolve().parents[2],
]
SERVICE_RECORD = next((p for p in _candidates if p and (p / 'engine.py').exists()), None)
if SERVICE_RECORD is None:
    raise SystemExit(
        'service-record source not found; set SERVICE_RECORD_REPO to the copied or cloned '
        'service-record directory before running this experiment'
    )
sys.path.insert(0, str(SERVICE_RECORD))

from engine import compute, load_config
from notary import append, read_entries
from referral import recommend


def add_transaction(folder, task_run_id, seller, result='pass'):
    common = {'task_run_id': task_run_id, 'seller': seller, 'buyer': 'project-manager', 'domain': 'arithmetic'}
    append('commit', {**common, 'claim': 'complete the task', 'confidence': .85}, folder)
    append('stake', {**common, 'stake': {'kind': 'compute', 'amount': 1, 'proof': 'experiment'}}, folder)
    if result == 'fabrication':
        old = os.environ.get('NOTARY_CALLER')
        os.environ['NOTARY_CALLER'] = 'auditor'
        append('flag', {**common, 'type': 'fabrication', 'reason': 'delivery missing'}, folder)
        if old is None:
            os.environ.pop('NOTARY_CALLER', None)
        else:
            os.environ['NOTARY_CALLER'] = old
    append('outcome', {**common, 'result': 'fail' if result == 'fabrication' else result,
                       'note': 'machine checker', 'evidence': 'experiment'}, folder)


def main():
    with TemporaryDirectory(prefix='referral-misalignment-') as temp:
        records = Path(temp)
        for i in range(5):
            add_transaction(records, f'clean-{i}', 'seller-a')
        add_transaction(records, 'lie-1', 'seller-c', 'fabrication')
        trusted = compute(read_entries(records), load_config())

        poisoned = deepcopy(trusted)
        poisoned['seller-c']['character'] = 99
        poisoned['seller-a']['character'] = 20
        baseline = recommend(['seller-a', 'seller-c'], poisoned, 'arithmetic')

        mismatch = any(poisoned[seller] != trusted[seller]
                       for seller in ('seller-a', 'seller-c'))
        checked = trusted if mismatch else poisoned
        mitigated = recommend(['seller-a', 'seller-c'], checked, 'arithmetic')
        result = {
            'intended_behavior': 'recommend seller-a, the clean seller',
            'attack': 'reputation lookup tool reports seller-c=99 and seller-a=20',
            'baseline': {'lookup_trusted': True, **baseline},
            'change': 'recompute scores from notarised records and reject mismatched lookup',
            'mitigated': {'lookup_mismatch_detected': mismatch, **mitigated},
            'records': [{'seller': seller, 'character': trusted[seller]['character']}
                        for seller in ('seller-a', 'seller-c')],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Independent review probes. XFAIL means a known, unimplemented full-spec rule.

Run with --runxfail to expose failures. Whitewashing is checked against the
actual HW2 selection score (raw character); it is not a proof of the undefined
full-protocol expected-trust/sponsor-cost model.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import notary


def transaction(folder, name, seller='seller-a', buyer='buyer', confidence=.85,
                result='pass', fraud=False, buyer_owner=None):
    common = dict(task_run_id=name, seller=seller, buyer=buyer, domain='math')
    if buyer_owner is not None:
        common['buyer_owner'] = buyer_owner
    notary.append('commit', {**common, 'claim':'deliver', 'confidence':confidence}, folder)
    notary.append('stake', {**common, 'stake':{'kind':'compute','amount':1,'proof':'scripted-review'}}, folder)
    if fraud:
        notary.append('flag', {**common,'type':'fabrication','reason':'scripted missing file'}, folder)
    notary.append('outcome', {**common,'result':result,'note':'scripted checker verdict','evidence':'scripted-review'}, folder)


def scores(folder):
    return engine.compute(notary.read_entries(folder), engine.load_config())


def with_sponsorship(folder, newcomer):
    # Full spec 8.4 fields. Current HW2 rejects this kind at the notary;
    # supplying it to the pure engine also demonstrates missing replay support.
    entry = {'kind':'sponsorship','sponsor':'seller-b','newcomer':newcomer,
             'share':.1,'vesting_successes':10,'entry_id':'review-sponsorship',
             'notarised_at':'2026-09-26T00:00:00Z'}
    entry['sha256'] = notary.canonical_hash(entry)
    return engine.compute([entry] + notary.read_entries(folder), engine.load_config())


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='D19/D20: sponsorship and probation are absent')
def test_scenario_honest_newcomer(tmp_path):
    for i in range(10):
        transaction(tmp_path, str(i), seller='newcomer')
    result = with_sponsorship(tmp_path, 'newcomer')
    assert result['seller-b']['character'] > engine.load_config()['character_initial'], 'Sponsor receives no vested gain'
    assert result['newcomer'].get('status') == 'active', 'No probation/vesting status is computed'


def test_scenario_honest_miss(tmp_path):
    transaction(tmp_path, 'miss', confidence=.55, result='fail')
    score = scores(tmp_path)['seller-a']
    assert score['offences'] == 0
    assert score['character'] >= engine.load_config()['character_initial']
    assert score['professional']['math'] == pytest.approx(69.75)


def test_scenario_liar(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTARY_CALLER', 'auditor')
    for i in range(10):
        transaction(tmp_path, str(i))
    before = scores(tmp_path)['seller-a']['character']
    transaction(tmp_path, 'lie', fraud=True, result='fail')
    assert scores(tmp_path)['seller-a']['character'] == pytest.approx(before / 3)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='D20: sponsor loss-sharing is absent')
def test_scenario_liar_sponsor_loss(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTARY_CALLER', 'auditor')
    transaction(tmp_path, 'lie', fraud=True, result='fail')
    assert with_sponsorship(tmp_path, 'seller-a')['seller-b']['character'] < engine.load_config()['character_initial'], 'Sponsor bears no loss'


def test_scenario_repeat_offender(tmp_path, monkeypatch):
    monkeypatch.setenv('NOTARY_CALLER', 'auditor')
    transaction(tmp_path, 'lie1', fraud=True, result='fail')
    first = scores(tmp_path)['seller-a']['character']
    transaction(tmp_path, 'lie2', fraud=True, result='fail')
    final = scores(tmp_path)['seller-a']
    assert final['offences'] == 2
    assert final['character'] == pytest.approx(first / 9)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='9.5: fresh identity gets 40 with no admission cost or cap')
@pytest.mark.parametrize('clean_count', [0, 10, 50])
@pytest.mark.parametrize('offences', [1, 2, 3])
def test_whitewashing_selection_score_property(tmp_path, monkeypatch, clean_count, offences):
    monkeypatch.setenv('NOTARY_CALLER', 'auditor')
    for i in range(clean_count):
        transaction(tmp_path, f'clean{i}')
    for i in range(offences):
        transaction(tmp_path, f'lie{i}', fraud=True, result='fail')
    cfg = engine.load_config()
    cfg['sellers'] = ['seller-a', 'fresh-id']
    continuing = notary.read_entries(tmp_path)
    fresh = []
    # Exhaustive bounded sample, including the initial step. A single
    # counterexample refutes the universal invariant for this implementation.
    for step in range(41):
        kept = engine.compute(continuing, cfg)['seller-a']['character']
        reset = engine.compute(fresh, cfg)['fresh-id']['character']
        assert kept >= reset, f'clean={clean_count}, offences={offences}, step={step}: keep={kept}, reset={reset}'
        folder = tmp_path / f'future-{step}'
        transaction(folder, f'future{step}')
        nxt = notary.read_entries(folder)
        continuing.extend(nxt)
        renamed = copy.deepcopy(nxt)
        for entry in renamed:
            entry['seller'] = 'fresh-id'
            entry['sha256'] = notary.canonical_hash(entry)
        fresh.extend(renamed)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='9.1/9.8: owner-aware network and pair caps are absent')
def test_scenario_sybil_ring(tmp_path):
    for i in range(12):
        transaction(tmp_path, str(i), buyer=f'sybil-{i % 3}', buyer_owner='one-owner')
    result = scores(tmp_path)['seller-a']
    assert 'network' in result, 'No owner registry/network score; repeated counterparties earn full clean credit'
    assert result['network']['distinct_owners'] == 1


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='D21/9.6: evidence is not checked and buyer is not scored')
def test_scenario_dishonest_verifier(tmp_path):
    # The reviewer supplies a real success artifact/check result, but the
    # notary/engine accept a contradictory buyer report without scoring buyer.
    evidence = tmp_path / 'checker.json'
    evidence.write_text('{"result":"pass"}')
    common = dict(task_run_id='dishonest-buyer', seller='seller-a', buyer='buyer', domain='math')
    notary.append('commit', {**common,'claim':'deliver','confidence':.85}, tmp_path)
    notary.append('stake', {**common,'stake':{'kind':'compute','amount':1,'proof':'scripted-review'}}, tmp_path)
    notary.append('outcome', {**common,'result':'fail','note':'contradicts checker','evidence':str(evidence)}, tmp_path)
    assert scores(tmp_path).get('buyer', {}).get('offences', 0) == 1, 'Buyer contradiction causes no buyer offence'


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='D8/9.3: change events and re-verification are absent')
def test_scenario_model_upgrade(tmp_path):
    transaction(tmp_path, 'success')
    entries = notary.read_entries(tmp_path)
    before = scores(tmp_path)['seller-a']
    event = {'kind':'change','agent_id':'seller-a','event':'model_upgrade','from':'old','to':'new',
             'notarised_at':'2026-09-28T00:00:00Z','entry_id':'review-change'}
    event['sha256'] = notary.canonical_hash(event)
    after = engine.compute(entries + [event], engine.load_config())['seller-a']
    assert after['professional']['math'] == pytest.approx(before['professional']['math'] * .6), 'Model change is silently ignored'
    assert after.get('cap') == 70


def test_buyer_choice_changes_with_reputation_only():
    context = {'phase':'choice','available':['seller-c','seller-b','seller-a'],
               'high_stake':False,'human_threshold':40,'mode':'improved','domain':'math',
               'lookup':{s:{'character':40,'professional':{'math':50}} for s in ['seller-c','seller-b','seller-a']}}
    from protocol import parse_block
    def choose():
        p = subprocess.run([sys.executable,str(ROOT/'agents/mock_buyer.py')], input=json.dumps(context),text=True,capture_output=True,check=True)
        return parse_block(p.stdout, 'choice')['seller']
    assert choose() == 'seller-c'
    context['lookup']['seller-c']['character'] = 13.33
    assert choose() == 'seller-b'
    context['lookup']['seller-a']['character'] = 90
    assert choose() == 'seller-a'


def test_evaluation_discloses_deterministic_policies():
    # Check the generator so disclosure survives the next evaluation run.
    source = (ROOT/'evaluate.py').read_text()
    assert 'not a measured effect on real-model behaviour' in source
    assert 'baseline also uses reputation for the safety stop' in source

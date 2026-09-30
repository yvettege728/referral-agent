"""Pure functions for the mediated Referral Agent flow."""
import hashlib
import re


def recommend(available, scores, domain):
    if not available:
        raise ValueError('no candidates available')
    seller = max(available, key=lambda name: (scores[name]['character'], scores[name]['professional'].get(domain, 50)))
    confidence = round(max(0.05, min(0.95, scores[seller]['character'] / 100)), 2)
    return {'seller': seller, 'confidence': confidence, 'reason': 'Highest character, then professional score in this domain.'}


def score_recommendation(confidence, outcome):
    if outcome not in ('pass', 'fail'):
        raise ValueError('outcome must be pass or fail')
    actual = 1 if outcome == 'pass' else 0
    return 100 * (1 - (confidence - actual) ** 2)


def mediated_brief(raw_brief):
    return '\n'.join(line for line in raw_brief.splitlines() if not re.match(r'^\s*PRIVATE\s*:', line, re.I)).strip() + '\n'


def handoff_digest(brief):
    return hashlib.sha256(brief.encode('utf-8')).hexdigest()


def referral_reliability(entries, referral_id):
    choices = {}
    outcomes = {}
    for entry in entries:
        if entry.get('referral') != referral_id:
            continue
        task_run_id = entry.get('task_run_id')
        if entry.get('kind') == 'choice' and 'seller' in entry:
            confidence = entry.get('confidence', 0.5)
            if type(confidence) in (int, float) and 0 <= confidence <= 1:
                choices[task_run_id] = float(confidence)
        elif entry.get('kind') == 'outcome' and entry.get('result') in ('pass', 'fail'):
            outcomes[task_run_id] = entry['result']
    completed = [(choices[task], outcomes[task]) for task in choices if task in outcomes]
    if not completed:
        return {'recommendations': len(choices), 'completed': 0, 'successes': 0, 'reliability': 50.0}
    total_error = sum((confidence - (1 if result == 'pass' else 0)) ** 2 for confidence, result in completed)
    return {'recommendations': len(choices), 'completed': len(completed),
            'successes': sum(result == 'pass' for _, result in completed),
            'reliability': round(100 * (1 - total_error / len(completed)), 2)}

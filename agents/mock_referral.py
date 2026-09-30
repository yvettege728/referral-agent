"""Deterministic Referral Agent for the mediated prototype."""
import json
import sys
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import emit
from team import ROLE_ORDER, synthesize


def main():
    context = json.load(sys.stdin)
    if context['phase'] == 'outcome':
        emit('outcome', {'result': context['check_result'], 'note': context['check_reason']})
        return
    available = context['available']
    if context['high_stake'] or not available:
        emit('choice', {'action': 'ask_human', 'reason': 'High-stake task or no candidates remain.'})
        return
    team_context = {key: context[key] for key in ('available', 'domain', 'mode', 'brief', 'high_stake', 'human_threshold', 'role_weights') if key in context}
    if 'lookup' in context:
        team_context['lookup'] = context['lookup']
    opinions = []
    root = Path(__file__).resolve().parents[1]
    for role in ROLE_ORDER:
        proc = subprocess.run([sys.executable, str(root / 'agents' / 'mock_team_member.py'), role],
                              input=json.dumps(team_context), text=True, capture_output=True, check=True)
        opinions.append(json.loads(proc.stdout))
    team = {'opinions': opinions, 'lead': synthesize(opinions, team_context)}
    trace_path = context.get('team_trace_path')
    if trace_path:
        Path(trace_path).write_text(json.dumps(team, indent=2) + '\n')
    scores = context.get('lookup', {})
    if context['mode'] == 'baseline':
        scores = {seller: {'character': 40, 'professional': {context['domain']: 50}} for seller in available}
    if all(scores[seller]['character'] < context['human_threshold'] for seller in available):
        emit('choice', {'action': 'ask_human', 'reason': 'Every remaining candidate is below the character threshold.'})
        return
    result = dict(team['lead'])
    forced = context.get('forced_seller')
    if forced:
        result = {'seller': forced, 'confidence': 0.5, 'reason': 'Explicit evaluation intervention: forced first pick of ' + forced, 'dissent': team['lead'].get('dissent', [])}
    emit('choice', result)


if __name__ == '__main__':
    main()

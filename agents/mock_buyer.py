#!/usr/bin/env python3
"""Read only the buyer context supplied on stdin; emit the common protocol."""
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import emit


def main():
    context = json.load(sys.stdin)
    if context['phase'] == 'outcome':
        emit('outcome', {'result':context['check_result'], 'note':context['check_reason']})
        return
    available = context['available']
    if context['high_stake'] or not available:
        emit('choice', {'action':'ask_human', 'reason':'High-stake task or no candidates remain.'})
        return
    if context['mode'] == 'improved':
        scores = context['lookup']
        if all(scores[s]['character'] < context['human_threshold'] for s in available):
            emit('choice', {'action':'ask_human', 'reason':'Every remaining candidate is below the character threshold.'})
            return
        order = sorted(available, key=lambda s: (scores[s]['character'], scores[s]['professional'][context['domain']]), reverse=True)
        reason = 'Highest character, then professional score in this domain; stable order breaks complete ties.'
    else:
        order = [s for s in re.findall(r'^## (seller-[abc])\s*$',context['self_descriptions'],re.M) if s in available]
        reason = 'First available seller in the supplied self-descriptions.'
    seller = context.get('forced_seller') or order[0]
    if context.get('forced_seller'):
        reason = 'Explicit evaluation intervention: forced first pick of '+seller
    emit('choice', {'seller':seller,'reason':reason})


if __name__ == '__main__':
    main()

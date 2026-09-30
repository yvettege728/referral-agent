"""Strict shared transcript contract for mock and future real agents."""
import json
import math
from pathlib import Path
import re


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_block(text, kind):
    blocks = re.findall(r'^```' + re.escape(kind) + r'[ \t]*\n(.*?)^```[ \t]*$', text, re.M | re.S)
    if len(blocks) != 1:
        raise ValueError(f'expected exactly one {kind} block, got {len(blocks)}')
    obj = json.loads(blocks[0], object_pairs_hook=unique_object,
                     parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'invalid number: {value}')))
    if not isinstance(obj, dict):
        raise ValueError('block must contain one JSON object')
    fields = {'choice':['reason'], 'commit':['claim','confidence'],
              'delivery':['path','summary'], 'outcome':['result','note']}[kind]
    for field in fields:
        if field not in obj or (field != 'confidence' and (not isinstance(obj[field],str) or not obj[field].strip())):
            raise ValueError(f'missing or invalid {kind}.{field}')
    if kind == 'choice':
        if obj.get('action') == 'ask_human':
            if 'seller' in obj:
                raise ValueError('choice cannot both select and ask_human')
        elif not isinstance(obj.get('seller'), str) or not obj['seller'] or 'action' in obj:
            raise ValueError('choice requires seller or action ask_human')
        if 'confidence' in obj:
            c = obj['confidence']
            if type(c) not in (int, float) or not 0 <= c <= 1 or not math.isfinite(c):
                raise ValueError('choice confidence must be finite and in [0,1]')
    if kind == 'commit':
        c = obj['confidence']
        if type(c) not in (int,float) or not 0 <= c <= 1 or not math.isfinite(c):
            raise ValueError('confidence must be finite and in [0,1]')
    if kind == 'delivery' and not Path(obj['path']).is_absolute():
        raise ValueError('delivery path must be absolute')
    if kind == 'outcome' and obj['result'] not in ('pass','fail'):
        raise ValueError('outcome result must be pass or fail')
    return obj


def emit(kind, payload):
    print(f'```{kind}\n{json.dumps(payload, ensure_ascii=False, allow_nan=False)}\n```')

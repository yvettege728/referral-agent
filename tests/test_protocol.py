import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parser():
    assert (ROOT/'protocol.py').exists(), 'shared protocol parser is required'
    return importlib.import_module('protocol').parse_block


def test_parse_valid():
    assert parser()('text\n```choice\n{"seller":"seller-a","reason":"record"}\n```\n', 'choice')['seller'] == 'seller-a'

@pytest.mark.parametrize('text,kind', [
    ('no fenced block', 'choice'),
    ('```choice\n{bad}\n```', 'choice'),
    ('```choice\n{"seller":"seller-a"}\n```', 'choice'),
    ('```commit\n{"claim":"work","confidence":2}\n```', 'commit'),
    ('```commit\n{"claim":"work","confidence":NaN}\n```', 'commit'),
    ('```delivery\n{"path":"relative.csv","summary":"done"}\n```', 'delivery'),
    ('```outcome\n{"result":"maybe","note":"hmm"}\n```', 'outcome'),
    ('```choice\n{"action":"ask_human","seller":"seller-a","reason":"x"}\n```', 'choice'),
    ('```choice\n{"seller":"seller-a","seller":"seller-b","reason":"x"}\n```', 'choice'),
    ('```choice\n{"seller":"seller-a","reason":"x"}\n```\n```choice\n{"seller":"seller-b","reason":"x"}\n```', 'choice'),
])
def test_parse_rejects_invalid(text, kind):
    with pytest.raises(ValueError):
        parser()(text, kind)


def test_huge_integer_confidence_rejected():
    import json
    with pytest.raises(ValueError,match='confidence'):
        parser()('```commit\n'+json.dumps({'claim':'work','confidence':10**400})+'\n```','commit')

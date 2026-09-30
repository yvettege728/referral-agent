#!/usr/bin/env python3
"""Verify factorisation using multiplication and primality, independently of seller."""
import json
import math
from pathlib import Path
import sys


def check(path):
    numbers = json.loads(Path(__file__).with_name('numbers.json').read_text())
    answer = json.loads(Path(path).read_text())
    if not isinstance(answer, dict) or set(answer) != {str(n) for n in numbers}:
        raise ValueError('JSON keys must match the input numbers')
    for n in numbers:
        factors = answer[str(n)]
        if not isinstance(factors, list) or any(type(f) is not int or f < 2 for f in factors):
            raise ValueError(f'{n}: factors must be integers >= 2')
        if factors != sorted(factors) or math.prod(factors) != n:
            raise ValueError(f'{n}: wrong product or factor order')
        if any(any(f % d == 0 for d in range(2, math.isqrt(f)+1)) for f in factors):
            raise ValueError(f'{n}: a factor is not prime')


if __name__ == '__main__':
    try:
        check(sys.argv[1])
    except (OSError, ValueError, TypeError, IndexError) as exc:
        print('FAIL: ' + str(exc).replace('\n', ' '))
        sys.exit(1)
    print('PASS: every prime factorisation is correct')

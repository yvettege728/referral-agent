#!/usr/bin/env python3
"""Independent expected values calculated from the supplied conversion definitions."""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

EXPECTED = [('flour', '180.00'), ('sugar', '100.00'), ('butter', '56.75'), ('chocolate', '85.05')]


def check(path):
    with Path(path).open(newline='') as source:
        rows = list(csv.reader(source))
    if not rows or rows[0] != ['ingredient', 'grams'] or len(rows) != len(EXPECTED)+1:
        raise ValueError('wrong CSV header or row count')
    for row, (ingredient, grams) in zip(rows[1:], EXPECTED):
        if len(row) != 2 or row[0] != ingredient:
            raise ValueError('wrong ingredient, order, or column count')
        value = Decimal(row[1])
        if not value.is_finite() or value != Decimal(grams):
            raise ValueError(ingredient + ': incorrect grams')


if __name__ == '__main__':
    try:
        check(sys.argv[1])
    except (OSError, ValueError, InvalidOperation, IndexError, csv.Error) as exc:
        print('FAIL: ' + str(exc).replace('\n', ' '))
        sys.exit(1)
    print('PASS: all conversions match the supplied definitions')

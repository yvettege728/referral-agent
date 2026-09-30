#!/usr/bin/env python3
import csv
from pathlib import Path
import sys

EXPECTED = [
    ['id', 'name', 'email', 'city'],
    ['1', 'Ada Lovelace', 'ada@example.com', 'London'],
    ['2', 'Grace Hopper', 'grace@example.com', 'New York'],
    ['3', 'Lin Chen', 'lin@example.com', 'Boston'],
]


def check(path):
    with Path(path).open(newline='') as source:
        if list(csv.reader(source)) != EXPECTED:
            raise ValueError('header, normalisation, deduplication, or row order is wrong')


if __name__ == '__main__':
    try:
        check(sys.argv[1])
    except (OSError, ValueError, IndexError, csv.Error) as exc:
        print('FAIL: ' + str(exc).replace('\n', ' '))
        sys.exit(1)
    print('PASS: cleaned contacts match the required rules')

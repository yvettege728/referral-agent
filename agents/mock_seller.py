#!/usr/bin/env python3
"""Scripted sellers. SR_PHASE separates notarised commitment from actual work."""
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import emit


def produce(task_id, task_dir, path, hesitant):
    if task_id == '01':
        result = {}
        for original in json.loads((task_dir/'numbers.json').read_text()):
            n, divisor, factors = original, 2, []
            while divisor * divisor <= n:
                while n % divisor == 0:
                    factors.append(divisor)
                    n //= divisor
                divisor += 1
            if n > 1:
                factors.append(n)
            result[str(original)] = factors
        path.write_text(json.dumps(result, indent=2)+'\n')
        return
    with path.open('w', newline='') as out:
        writer = csv.writer(out)
        if task_id == '03':
            with (task_dir/'messy.csv').open(newline='') as source:
                rows = list(csv.reader(source))[1:]
            cleaned = {}
            for row in rows:
                key = int(row[0].strip())
                cleaned.setdefault(key, [str(key), ' '.join(row[1].split()), row[2].strip().lower(), ' '.join(row[3].split())])
            writer.writerow(['id','name','email','city'])
            writer.writerows(cleaned[key] for key in sorted(cleaned))
            return
        units = json.loads((task_dir/'units.json').read_text())
        with (task_dir/'recipe.csv').open(newline='') as source:
            rows = list(csv.DictReader(source))
        writer.writerow(['ingredient','grams'])
        for row in rows:
            ingredient, unit = row['ingredient'], row['unit']
            if unit == 'oz' or (hesitant and unit == 'US fl oz'):
                factor = Decimal(units['grams_per_oz'])
            elif unit == 'US fl oz':
                factor = Decimal(units['ml_per_US_fl_oz']) * Decimal(units['density_g_per_ml'][ingredient])
            else:
                factor = Decimal(units['grams_per_'+unit.replace(' ','_')][ingredient])
            grams = (Decimal(row['quantity'])*factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            writer.writerow([ingredient, str(grams)])


def main():
    seller, task_id = sys.argv[1:3]
    if seller not in ('seller-a','seller-b','seller-c') or task_id not in ('01','02','03','04'):
        raise ValueError('unknown seller or task')
    task_dir = Path(os.environ.get('SR_TASK_DIR', ROOT/'tasks'/task_id))
    name = json.loads((task_dir/'task.json').read_text())['delivery_name']
    path = Path(os.environ.get('SR_DELIVERY_PATH', Path.cwd()/name)).absolute()
    phase = os.environ.get('SR_PHASE','all')
    confidence = .9 if seller == 'seller-c' else (.45 if seller == 'seller-b' and task_id == '04' else .85)
    if phase in ('commit','all'):
        emit('commit', {'claim':f'I will produce the required {name}', 'confidence':confidence})
    if phase in ('delivery','all'):
        if seller != 'seller-c':
            produce(task_id, task_dir, path, seller == 'seller-b' and task_id == '04')
        emit('delivery', {'path':str(path), 'summary':'Completed the requested file.'})


if __name__ == '__main__':
    main()

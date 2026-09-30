import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOOD = {
    '01': json.dumps({'1': [], '12': [2, 2, 3], '97': [97], '360': [2, 2, 2, 3, 3, 5], '1024': [2]*10, '99991': [99991]}),
    '02': 'ingredient,grams\nflour,180.00\nsugar,100.00\nbutter,56.75\nchocolate,85.05\n',
    '03': 'id,name,email,city\n1,Ada Lovelace,ada@example.com,London\n2,Grace Hopper,grace@example.com,New York\n3,Lin Chen,lin@example.com,Boston\n',
    '04': 'ingredient,grams\nhoney,85.05\nwater,59.15\nflour,150.00\nbrown sugar,165.00\nolive oil,40.37\n',
}

@pytest.mark.parametrize('task', GOOD)
def test_checker_accepts_correct_delivery(task, tmp_path):
    path = tmp_path / 'delivery'
    path.write_text(GOOD[task])
    result = subprocess.run([sys.executable, str(ROOT/'tasks'/task/'check.py'), str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert len(result.stdout.splitlines()) == 1

@pytest.mark.parametrize('task', GOOD)
def test_checker_rejects_wrong_delivery(task, tmp_path):
    path = tmp_path / 'delivery'
    path.write_text('{}' if task == '01' else 'ingredient,grams\nwrong,1\n')
    checker = ROOT/'tasks'/task/'check.py'
    assert checker.exists(), 'checker must exist'
    result = subprocess.run([sys.executable, str(checker), str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert len(result.stdout.splitlines()) == 1

@pytest.mark.parametrize('task', GOOD)
def test_checker_missing_delivery(task, tmp_path):
    checker = ROOT/'tasks'/task/'check.py'
    assert checker.exists(), 'checker must exist'
    result = subprocess.run([sys.executable, str(checker), str(tmp_path/'missing')], capture_output=True, text=True)
    assert result.returncode == 1
    assert len(result.stdout.splitlines()) == 1


@pytest.mark.parametrize('task', GOOD)
def test_capable_mock_seller_passes_actual_checker(task,tmp_path):
    import os
    path=tmp_path/'delivery'
    seller=subprocess.run([sys.executable,str(ROOT/'agents/mock_seller.py'),'seller-a',task],cwd=tmp_path,env={**os.environ,'SR_DELIVERY_PATH':str(path),'SR_PHASE':'delivery'},capture_output=True,text=True)
    assert seller.returncode==0,seller.stderr
    checked=subprocess.run([sys.executable,str(ROOT/'tasks'/task/'check.py'),str(path)],capture_output=True,text=True)
    assert checked.returncode==0,checked.stdout+checked.stderr


def test_hard_task_correct_volume_conversion(tmp_path):
    # 1.5 US fl oz * 29.5735295625 ml/fl oz * .910 g/ml = 40.3678678528125 g.
    path=tmp_path/'delivery.csv'
    path.write_text(GOOD['04'].replace('40.39','40.37'))
    result=subprocess.run([sys.executable,str(ROOT/'tasks/04/check.py'),str(path)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr

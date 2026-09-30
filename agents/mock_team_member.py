"""Mock subprocess for one internal Referral Team employee."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from team import opinion_for


def main():
    role = sys.argv[1]
    context = json.load(sys.stdin)
    print(json.dumps(opinion_for(role, context)))


if __name__ == '__main__':
    main()

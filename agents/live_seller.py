#!/usr/bin/env python3
"""Bounded live seller: model proposes content; adapter writes only assigned path."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openai_responses import call_json
from protocol import emit


def _inputs(directory, delivery):
    result = {}
    total = 0
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.is_symlink() or path.resolve() == delivery.resolve():
            continue
        data = path.read_text(errors="replace")
        total += len(data.encode("utf-8"))
        if total > 100_000:
            raise RuntimeError("seller input files exceed 100 KB")
        result[path.name] = data
    return result


def run_commit(context, role, caller=call_json):
    schema = {
        "type": "object",
        "properties": {"claim": {"type": "string"},
                       "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
        "required": ["claim", "confidence"], "additionalProperties": False,
    }
    instructions = (ROOT / "agents" / "prompts" / "seller-common.md").read_text() + "\n\n" + \
        (ROOT / "agents" / "prompts" / f"{role}.md").read_text()
    return caller(instructions, {"brief": context["brief"]}, schema, "seller_commitment")


def run_delivery(context, role="seller-a", caller=call_json):
    directory = Path(context["input_directory"]).resolve()
    delivery = Path(context["delivery_path"]).resolve()
    if delivery.parent != directory or delivery.is_symlink():
        raise RuntimeError("delivery path must be a non-symlink file directly inside the assigned work directory")
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}, "content": {"type": "string"}},
        "required": ["summary", "content"], "additionalProperties": False,
    }
    instructions = (ROOT / "agents" / "prompts" / "seller-common.md").read_text() + "\n\n" + \
        (ROOT / "agents" / "prompts" / f"{role}.md").read_text() + \
        "\n\nYou cannot write files directly. Return the complete delivery file as content. The adapter writes it. " \
        "The content field must contain only the file bytes, with no Markdown fences, explanation, or ellipsis. " \
        "For tabular tasks, preserve every required row and column: apply the brief mechanically, keep the first " \
        "occurrence of each numeric ID in input order, and do not invent, omit, merge, or summarize rows. " \
        "Before returning, mentally check that the content is a complete parseable CSV with the requested header."
    payload = {"brief": context["brief"], "commitment": context.get("commitment"),
               "input_files": _inputs(directory, delivery), "delivery_filename": delivery.name}
    result, metadata = caller(instructions, payload, schema, "seller_delivery")
    delivery.write_text(result["content"])
    return {"path": str(delivery), "summary": result["summary"]}, metadata


def main():
    role = sys.argv[1]
    prompt_path = Path(sys.argv[2])
    context = json.load(sys.stdin)
    if context.get("phase") == "commit":
        result, metadata = run_commit(context, role)
        kind = "commit"
    elif context.get("phase") == "delivery":
        result, metadata = run_delivery(context, role)
        kind = "delivery"
    else:
        raise RuntimeError("unknown seller phase")
    prompt_path.with_suffix(".model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    emit(kind, result)


if __name__ == "__main__":
    main()

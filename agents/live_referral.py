#!/usr/bin/env python3
"""Live model Referral panel and Lead synthesis for mediated runs."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openai_responses import call_json
from protocol import emit

ROLE_ORDER = ("buyer_liaison", "talent_scout", "research_analyst", "risk_partner")
ROLE_DIR = Path(__file__).resolve().parent / "roles"


def _opinion_schema(role):
    return {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": [role]},
            "seller": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "evidence": {"type": "string"},
            "concern": {"type": "string"},
        },
        "required": ["role", "seller", "confidence", "rationale", "evidence", "concern"],
        "additionalProperties": False,
    }


def _lead_schema(available):
    return {
        "type": "object",
        "properties": {
            "seller": {"type": "string", "enum": list(available)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
            "dissent": {"type": "array", "items": {
                "type": "object",
                "properties": {"role": {"type": "string"}, "seller": {"type": "string"},
                               "reason": {"type": "string"}},
                "required": ["role", "seller", "reason"], "additionalProperties": False,
            }},
        },
        "required": ["seller", "confidence", "reason", "dissent"],
        "additionalProperties": False,
    }


def _safe_context(context):
    keys = ("available", "domain", "mode", "brief", "high_stake", "human_threshold",
            "lookup", "self_descriptions", "forced_seller")
    return {key: context[key] for key in keys if key in context}


def _usage(metadata):
    return {
        "calls": len(metadata),
        "input_tokens": sum(item.get("input_tokens", 0) for item in metadata),
        "output_tokens": sum(item.get("output_tokens", 0) for item in metadata),
        "total_tokens": sum(item.get("total_tokens", 0) for item in metadata),
        "models": sorted({item.get("model") for item in metadata if item.get("model")}),
    }


def run_choice(context, caller=call_json):
    available = list(context.get("available", []))
    if context.get("high_stake") or not available:
        return {"action": "ask_human", "reason": "High-stake task or no candidates remain."}
    visible = _safe_context(context)
    opinions = []
    metadata = []
    for role in ROLE_ORDER:
        instructions = (ROLE_DIR / f"{role}.md").read_text()
        opinion, meta = caller(instructions, visible, _opinion_schema(role), f"{role}_opinion")
        if opinion.get("seller") is not None and opinion["seller"] not in available:
            raise RuntimeError(f"{role} selected an unavailable seller")
        opinions.append(opinion)
        metadata.append(meta)
    lead_payload = {"decision_context": visible, "independent_opinions": opinions}
    lead, lead_meta = caller((ROLE_DIR / "lead_referral.md").read_text(), lead_payload,
                             _lead_schema(available), "lead_referral_choice")
    metadata.append(lead_meta)
    if lead["seller"] not in available:
        raise RuntimeError("Lead Referral selected an unavailable seller")
    lead["decision_factors"] = [
        {"role": item["role"], "seller": item.get("seller"),
         "used": item.get("seller") == lead["seller"], "rationale": item["rationale"]}
        for item in opinions
    ]
    lead["confidence_calculation"] = {
        "method": "lead_model_judgment", "reported": lead["confidence"]
    }
    trace = {"opinions": opinions, "lead": lead, "model_calls": metadata,
             "model_usage": _usage(metadata)}
    trace_path = context.get("team_trace_path")
    if trace_path:
        Path(trace_path).write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")
    return lead


def run_outcome(context, caller=call_json):
    schema = {
        "type": "object",
        "properties": {"result": {"type": "string", "enum": ["pass", "fail"]},
                       "note": {"type": "string"}},
        "required": ["result", "note"], "additionalProperties": False,
    }
    result, metadata = caller(
        "Report the automatic check exactly. Never turn a failure into a pass or a pass into a failure.",
        context, schema, "referral_outcome")
    if result["result"] != context["check_result"]:
        raise RuntimeError("Referral outcome disagreed with the authoritative checker")
    return result, metadata


def main():
    prompt_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    context = json.load(sys.stdin)
    if context.get("phase") == "choice":
        result = run_choice(context)
        emit("choice", result)
        return
    result, metadata = run_outcome(context)
    if prompt_path:
        prompt_path.with_suffix(".model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    emit("outcome", result)


if __name__ == "__main__":
    main()

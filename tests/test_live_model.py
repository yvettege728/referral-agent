import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))


def test_ollama_gets_longer_outer_turn_timeout():
    from orchestrate import timeout_for
    assert timeout_for(30, "openai") == 30
    assert timeout_for(30, "ollama") == 300


def test_call_json_requires_api_key(monkeypatch):
    from openai_responses import call_json

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        call_json("Be concise.", {"question": "hello"}, {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }, "answer")


def test_call_json_posts_structured_request_and_returns_usage(monkeypatch):
    import openai_responses

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "id": "resp_test",
                "model": "gpt-test",
                "status": "completed",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": '{"answer":"ok"}'}
                ]}],
                "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16},
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr(openai_responses.urllib.request, "urlopen", fake_urlopen)
    result, metadata = openai_responses.call_json(
        "Return one answer.", {"question": "hello"}, {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }, "answer")

    assert result == {"answer": "ok"}
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["body"]["store"] is False
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert captured["body"]["text"]["format"]["strict"] is True
    assert metadata == {
        "response_id": "resp_test", "model": "gpt-test",
        "input_tokens": 12, "output_tokens": 4, "total_tokens": 16,
    }
    assert "test-secret" not in json.dumps(captured["body"])


def test_call_json_uses_local_ollama_without_api_key(monkeypatch):
    import openai_responses

    captured = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({
                "model": "qwen3:8b",
                "message": {"role": "assistant", "content": '{"answer":"local"}'},
                "prompt_eval_count": 9, "eval_count": 3,
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SR_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setattr(openai_responses.urllib.request, "urlopen", fake_urlopen)
    schema = {"type": "object", "properties": {"answer": {"type": "string"}},
              "required": ["answer"], "additionalProperties": False}
    result, metadata = openai_responses.call_json("Return JSON.", {"question": "hi"}, schema, "answer")

    assert result == {"answer": "local"}
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["format"] == schema
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["temperature"] == 0
    assert metadata["model"] == "qwen3:8b"
    assert metadata["input_tokens"] == 9
    assert metadata["output_tokens"] == 3


def test_live_referral_calls_independent_panel_then_lead_and_writes_trace(tmp_path):
    from live_referral import run_choice

    calls = []
    opinions = {
        "buyer_liaison_opinion": {"role": "buyer_liaison", "seller": "seller-b", "confidence": 0.66,
                                  "rationale": "The brief is clear.", "evidence": "brief", "concern": "Fit is uncertain."},
        "talent_scout_opinion": {"role": "talent_scout", "seller": "seller-b", "confidence": 0.71,
                                 "rationale": "Relevant capability.", "evidence": "domain record", "concern": "Limited history."},
        "research_analyst_opinion": {"role": "research_analyst", "seller": "seller-a", "confidence": 0.76,
                                     "rationale": "Cleaner record.", "evidence": "notary history", "concern": "Less domain data."},
        "risk_partner_opinion": {"role": "risk_partner", "seller": "seller-a", "confidence": 0.81,
                                 "rationale": "Lower integrity risk.", "evidence": "character score", "concern": "May be slower."},
    }

    def fake_call(instructions, payload, schema, schema_name):
        calls.append((schema_name, payload))
        if schema_name == "lead_referral_choice":
            return ({"seller": "seller-a", "confidence": 0.74,
                     "reason": "The cleaner record outweighs the speed advantage.",
                     "dissent": [{"role": "talent_scout", "seller": "seller-b", "reason": "Stronger immediate fit."}]},
                    {"response_id": "lead", "model": "gpt-test", "input_tokens": 20, "output_tokens": 8, "total_tokens": 28})
        value = opinions[schema_name]
        return value, {"response_id": schema_name, "model": "gpt-test", "input_tokens": 10,
                       "output_tokens": 5, "total_tokens": 15}

    trace = tmp_path / "team.json"
    context = {
        "phase": "choice", "available": ["seller-c", "seller-b", "seller-a"],
        "domain": "data-cleaning", "mode": "improved", "high_stake": False,
        "human_threshold": 40, "brief": "Clean a contact table.",
        "lookup": {seller: {"character": 60, "professional": {"data-cleaning": 70}}
                   for seller in ("seller-a", "seller-b", "seller-c")},
        "team_trace_path": str(trace),
    }
    choice = run_choice(context, caller=fake_call)

    assert [name for name, _ in calls[:4]] == [
        "buyer_liaison_opinion", "talent_scout_opinion",
        "research_analyst_opinion", "risk_partner_opinion",
    ]
    assert calls[4][0] == "lead_referral_choice"
    assert choice["seller"] == "seller-a"
    assert choice["dissent"][0]["role"] == "talent_scout"
    saved = json.loads(trace.read_text())
    assert len(saved["opinions"]) == 4
    assert saved["model_usage"]["calls"] == 5
    assert saved["model_usage"]["input_tokens"] == 60
    assert saved["model_usage"]["output_tokens"] == 28
    assert saved["lead"]["decision_factors"]


def test_live_seller_writes_only_the_assigned_delivery_path(tmp_path):
    from live_seller import run_delivery

    assigned = tmp_path / "delivery.csv"
    context = {
        "phase": "delivery", "brief": "Write the required contact CSV.",
        "input_directory": str(tmp_path), "delivery_path": str(assigned),
        "commitment": {"claim": "I will write delivery.csv", "confidence": 0.8},
    }

    def fake_call(instructions, payload, schema, schema_name):
        assert schema_name == "seller_delivery"
        return ({"summary": "Cleaned contacts.", "content": "id,name,email,city\n1,A,a@example.com,Boston\n"},
                {"response_id": "seller", "model": "gpt-test", "input_tokens": 15,
                 "output_tokens": 9, "total_tokens": 24})

    claim, metadata = run_delivery(context, caller=fake_call)
    assert claim == {"path": str(assigned), "summary": "Cleaned contacts."}
    assert assigned.read_text() == "id,name,email,city\n1,A,a@example.com,Boston\n"
    assert metadata["model"] == "gpt-test"
    assert not (tmp_path / "other.csv").exists()


def test_controlled_seller_c_needs_no_api_key(tmp_path):
    workdir = tmp_path / "seller-c"
    workdir.mkdir()
    (workdir / "task.json").write_text(json.dumps({"delivery_name": "delivery.csv"}))
    delivery = workdir / "delivery.csv"
    env = {**os.environ, "SR_PHASE": "delivery", "SR_TASK_ID": "03",
           "SR_TASK_DIR": str(workdir), "SR_DELIVERY_PATH": str(delivery)}
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        ["bash", str(ROOT / "agents" / "call_agent.sh"), "seller-c",
         str(workdir / "prompt.md"), str(workdir)],
        input="{}", text=True, capture_output=True, env=env, cwd=workdir)
    assert result.returncode == 0, result.stderr
    assert "```delivery" in result.stdout
    assert not delivery.exists()


def test_hybrid_run_uses_live_panel_controlled_adversary_and_live_honest_seller(tmp_path):
    requests = []
    lead_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_POST(self):
            nonlocal lead_calls
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length))
            requests.append(body)
            name = body["text"]["format"]["name"]
            payload = json.loads(body["input"][0]["content"][0]["text"])
            if name.endswith("_opinion"):
                role = name.removesuffix("_opinion")
                available = payload["available"]
                seller = "seller-c" if "seller-c" in available else "seller-b"
                value = {"role": role, "seller": seller, "confidence": 0.7,
                         "rationale": "Evidence-backed test opinion.", "evidence": "provided record",
                         "concern": "Limited observations."}
            elif name == "lead_referral_choice":
                lead_calls += 1
                seller = "seller-c" if lead_calls == 1 else "seller-b"
                value = {"seller": seller, "confidence": 0.68,
                         "reason": "Selected after comparing independent opinions.", "dissent": []}
            elif name == "referral_outcome":
                value = {"result": payload["check_result"], "note": payload["check_reason"]}
            elif name == "seller_commitment":
                value = {"claim": "I will write the cleaned contact CSV.", "confidence": 0.84}
            elif name == "seller_delivery":
                value = {"summary": "Cleaned and deduplicated contacts.",
                         "content": "id,name,email,city\n1,Ada Lovelace,ada@example.com,London\n2,Grace Hopper,grace@example.com,New York\n3,Lin Chen,lin@example.com,Boston\n"}
            else:
                raise AssertionError(name)
            response = json.dumps({
                "id": "resp_" + str(len(requests)), "model": "gpt-test", "status": "completed",
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps(value)}
                ]}],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    label = "hybrid-" + str(os.getpid()) + "-" + tmp_path.name
    env = {**os.environ, "PYTHON": sys.executable, "OPENAI_API_KEY": "fake",
           "OPENAI_MODEL": "gpt-test", "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "SR_RECORDS_DIR": str(tmp_path / "records")}
    try:
        result = subprocess.run(
            ["bash", str(ROOT / "run.sh"), "03", label, "--mediated", "--live"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = ROOT / "runs" / label
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["status"] == "pass"
    assert metrics["bad_deliveries"] == 1
    assert metrics["retries"] == 1
    assert metrics["execution_mode"] == "hybrid-live-model"
    assert metrics["model_calls"] == 14
    assert metrics["model_input_tokens"] == 140
    assert metrics["model_output_tokens"] == 70
    assert metrics["model_names"] == ["gpt-test"]
    assert len(requests) == 14
    assert all(request["store"] is False for request in requests)
    assert "fabrication" in (run_dir / "audit.txt").read_text()
    assert (run_dir / "attempt-2" / "seller-b" / "delivery.csv").exists()

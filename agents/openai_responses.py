"""Small standard-library client for structured OpenAI Responses API calls."""
import json
import os
import urllib.error
import urllib.request


def _output_text(response):
    chunks = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise RuntimeError("model refused the structured request: " + str(content.get("refusal", "")))
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    if not chunks:
        raise RuntimeError("OpenAI response contained no output_text")
    return "".join(chunks)


def _decode_object(text):
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("model structured output was not valid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("model structured output must be one JSON object")
    return result


def _call_ollama(instructions, payload, schema):
    model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps({"input": payload, "output_schema": schema}, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "300"))) as handle:
            response = json.loads(handle.read())
    except urllib.error.URLError as exc:
        raise RuntimeError("Ollama request failed; ensure the Ollama app is running: " + str(exc.reason)) from exc
    message = response.get("message") or {}
    result = _decode_object(message.get("content", ""))
    input_tokens = int(response.get("prompt_eval_count", 0))
    output_tokens = int(response.get("eval_count", 0))
    return result, {"response_id": None, "model": response.get("model", model),
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens}


def call_json(instructions, payload, schema, schema_name):
    provider = os.environ.get("SR_MODEL_PROVIDER", "openai").lower()
    if provider == "ollama":
        return _call_ollama(instructions, payload, schema)
    if provider != "openai":
        raise RuntimeError("unknown SR_MODEL_PROVIDER: " + provider)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for non-mock model execution")
    model = os.environ.get("OPENAI_MODEL", "gpt-5")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": model,
        "store": False,
        "instructions": instructions,
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
        }],
        "text": {"format": {
            "type": "json_schema",
            "name": schema_name,
            "schema": schema,
            "strict": True,
        }},
    }
    request = urllib.request.Request(
        base + "/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))) as handle:
            response = json.loads(handle.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("OpenAI API request failed: " + str(exc.reason)) from exc
    if response.get("status") not in (None, "completed"):
        raise RuntimeError("OpenAI response did not complete: " + str(response.get("status")))
    result = _decode_object(_output_text(response))
    usage = response.get("usage") or {}
    metadata = {
        "response_id": response.get("id"),
        "model": response.get("model", model),
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
    return result, metadata

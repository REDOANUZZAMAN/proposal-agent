"""Minimal OpenAI-compatible chat client (stdlib only). Config: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (env or .env)."""
import json, os, time, urllib.error, urllib.request


def _env(k):
    if k in os.environ:
        return os.environ[k]
    try:
        for line in open(os.path.join(os.path.dirname(__file__), ".env")):
            if line.startswith(k + "="):
                return line.rstrip("\n").split("=", 1)[1]
    except OSError:
        pass
    return ""


def chat(system, user, temperature=0.4, json_mode=False):
    body = {"model": _env("LLM_MODEL"), "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(_env("LLM_BASE_URL").rstrip("/") + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "proposal-agent/1.0", "Authorization": "Bearer " + _env("LLM_API_KEY")})
    for attempt in range(5):                    # free tiers rate-limit (429): wait and retry
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == 4:
                raise
            time.sleep(min(float(e.headers.get("Retry-After") or 0) or 5 * 2 ** attempt, 60))


def chat_json(system, user):
    return json.loads(chat(system, user, 0.2, json_mode=True))

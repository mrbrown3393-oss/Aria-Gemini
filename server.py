#!/usr/bin/env python3
"""Aria local server using Google's Gemini API; standard library only.

Set GEMINI_API_KEY in the environment, then run: python3 server.py
Open http://127.0.0.1:8080 in Safari.
"""
import json
import os
import uuid
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
MODEL = os.environ.get("ARIA_MODEL", "gemini-2.5-flash")
PORT = int(os.environ.get("PORT", "8080"))

SYSTEM = """You are Aria, a warm, quick, voice-first personal assistant living on the user's iPhone.
Your replies are spoken aloud, so keep them concise, natural, and easy to say out loud.
You can act on the phone through tools. iOS has no general remote control, so everything goes through
URL schemes and Apple Shortcuts:
- open_url: open a URL or iOS URL scheme on the phone.
- run_shortcut: run an Apple Shortcut by its exact name, optionally with text input.
- set_expression: change your avatar's expression to neutral, happy, curious, or concerned.
Say briefly what you are about to do before calling a tool. Never claim an action succeeded unless
the tool result says it was launched. Ask before anything destructive, costly, or that contacts others.
If you do not know a shortcut's exact name, ask the user."""

TOOLS = [
    {"name": "open_url", "description": "Open a URL or iOS URL scheme on the phone (tel:, sms:, maps://, https://, etc.).",
     "parameters": {"type": "OBJECT", "properties": {
         "url": {"type": "STRING", "description": "URL or iOS URL scheme to open"},
         "why": {"type": "STRING", "description": "Short reason shown to the user"}}, "required": ["url", "why"]}},
    {"name": "run_shortcut", "description": "Run an Apple Shortcut by exact name, optionally with text input.",
     "parameters": {"type": "OBJECT", "properties": {
         "name": {"type": "STRING", "description": "Exact Shortcut name"},
         "input": {"type": "STRING", "description": "Optional text input"},
         "why": {"type": "STRING", "description": "Short reason shown to the user"}}, "required": ["name", "why"]}},
    {"name": "set_expression", "description": "Set the avatar facial expression.",
     "parameters": {"type": "OBJECT", "properties": {
         "mood": {"type": "STRING", "enum": ["neutral", "happy", "curious", "concerned"]}}, "required": ["mood"]}},
]


def to_gemini_contents(messages):
    contents = []
    tool_names = {}
    for msg in messages[-40:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            parts = []
            if isinstance(content, str):
                parts = [{"text": content}]
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id", "")
                        name = tool_names.get(tool_id)
                        if name:
                            parts.append({"functionResponse": {"name": name,
                                "response": {"result": str(block.get("content", ""))}}})
                        else:
                            parts.append({"text": str(block.get("content", ""))})
                    elif isinstance(block.get("text"), str):
                        parts.append({"text": block["text"]})
            if parts:
                contents.append({"role": "user", "parts": parts})
        elif role == "assistant":
            parts = []
            if isinstance(content, str):
                parts = [{"text": content}]
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        parts.append({"text": block["text"]})
                    elif block.get("type") == "tool_use" and isinstance(block.get("name"), str):
                        tool_id = block.get("id", "")
                        tool_names[tool_id] = block["name"]
                        parts.append({"functionCall": {"name": block["name"], "args": block.get("input") or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
    return contents


def call_gemini(messages):
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": to_gemini_contents(messages),
        "tools": [{"function_declarations": TOOLS}],
        "tool_config": {"function_calling_config": {"mode": "AUTO"}},
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 900},
    }
    data = json.dumps(body).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "content-type": "application/json", "x-goog-api-key": KEY})
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read())
    candidates = result.get("candidates") or []
    if not candidates:
        feedback = result.get("promptFeedback", {})
        raise RuntimeError("Gemini returned no response. " + json.dumps(feedback, ensure_ascii=False))
    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = []
    for part in parts:
        if isinstance(part.get("text"), str) and part["text"].strip():
            content.append({"type": "text", "text": part["text"]})
        call = part.get("functionCall")
        if isinstance(call, dict) and call.get("name"):
            content.append({"type": "tool_use", "id": "gemini_" + uuid.uuid4().hex,
                            "name": call["name"], "input": call.get("args") or {}})
    return {"content": content}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data, content_type="application/json; charset=utf-8"):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(ROOT, "index.html"), "rb") as f:
                    return self.send_json(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                return self.send_json(500, {"error": "index.html is missing beside server.py"})
        if path == "/health":
            return self.send_json(200, {"ok": True, "provider": "Gemini", "model": MODEL,
                                        "api_key_configured": bool(KEY)})
        if path == "/manifest.json":
            return self.send_json(200, {"name": "Aria", "short_name": "Aria", "start_url": "/",
                "display": "standalone", "background_color": "#0b0f1a", "theme_color": "#0b0f1a"})
        return self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_json(404, {"error": "Not found"})
        if not KEY:
            return self.send_json(500, {"error": "GEMINI_API_KEY is not set in the shell running server.py"})
        try:
            size = int(self.headers.get("content-length", "0"))
            if size <= 0 or size > 1_000_000:
                return self.send_json(400, {"error": "Request body is empty or too large."})
            payload = json.loads(self.rfile.read(size))
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                return self.send_json(400, {"error": "Send at least one chat message."})
            self.send_json(200, call_gemini(messages))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("error", {}).get("message", raw)
            except (ValueError, AttributeError):
                detail = raw
            self.send_json(exc.code if 400 <= exc.code < 600 else 502,
                           {"error": f"Gemini API error ({exc.code}): {detail}"})
        except urllib.error.URLError as exc:
            self.send_json(502, {"error": f"Could not reach Gemini: {exc.reason}"})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Request body must be valid JSON."})
        except Exception as exc:
            self.send_json(500, {"error": str(exc) or exc.__class__.__name__})

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    if not KEY:
        print("WARNING: GEMINI_API_KEY is not set. Add it to the environment before chatting.")
    print(f"Aria listening on http://127.0.0.1:{PORT} (Gemini model {MODEL})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

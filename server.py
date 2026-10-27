#!/usr/bin/env python3
"""Local Aria chat server using Google's Gemini API. Standard library only."""
import json
import os
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
MODEL = os.environ.get("ARIA_MODEL", "gemini-2.5-flash")
PORT = int(os.environ.get("PORT", "8080"))
SYSTEM = ("You are Aria, a warm, concise voice-first personal assistant. "
          "Speak naturally and clearly. Do not claim to control the phone or run apps.")

def call_gemini(messages):
    contents = []
    for msg in messages[-30:]:
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            contents.append({"role": "user" if msg["role"] == "user" else "model",
                             "parts": [{"text": content}]})
    if not contents or contents[-1]["role"] != "user":
        raise ValueError("Please send a message to Aria.")
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 900},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", "x-goog-api-key": KEY})
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read())
    candidates = result.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    answer = "\n".join(p["text"] for p in parts if isinstance(p.get("text"), str)).strip()
    if not answer:
        raise RuntimeError("Gemini returned no text response.")
    return {"content": [{"type": "text", "text": answer}]}

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data, content_type="application/json; charset=utf-8"):
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
                    return self.reply(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                return self.reply(500, {"error": "index.html is missing beside server.py"})
        if path == "/health":
            return self.reply(200, {"ok": True, "provider": "Gemini", "model": MODEL,
                                    "api_key_configured": bool(KEY)})
        return self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.reply(404, {"error": "Not found"})
        if not KEY:
            return self.reply(500, {"error": "GEMINI_API_KEY is not set in the shell running server.py"})
        try:
            size = int(self.headers.get("content-length", "0"))
            if size <= 0 or size > 1_000_000:
                return self.reply(400, {"error": "Request body is empty or too large."})
            payload = json.loads(self.rfile.read(size))
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                return self.reply(400, {"error": "Send at least one chat message."})
            return self.reply(200, call_gemini(messages))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("error", {}).get("message", raw)
            except (ValueError, AttributeError):
                detail = raw
            return self.reply(exc.code, {"error": f"Gemini API error ({exc.code}): {detail}"})
        except urllib.error.URLError as exc:
            return self.reply(502, {"error": f"Could not reach Gemini: {exc.reason}"})
        except json.JSONDecodeError:
            return self.reply(400, {"error": "Request body must be valid JSON."})
        except Exception as exc:
            return self.reply(500, {"error": str(exc) or exc.__class__.__name__})

    def log_message(self, *_args):
        pass

if __name__ == "__main__":
    if not KEY:
        print("WARNING: GEMINI_API_KEY is not set. Add it to the environment before chatting.")
    print(f"Aria listening on http://127.0.0.1:{PORT} (Gemini model {MODEL})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

ARIA + GEMINI SETUP (iPhone iSH)

1. Keep these two files together: server.py and index.html.
2. In iSH, cd into the folder containing them.
3. Set your key for this shell session (replace the placeholder locally; do not send the key to anyone):
   export GEMINI_API_KEY='PASTE_YOUR_GEMINI_KEY_HERE'
4. Start Aria:
   python3 server.py
5. Open Safari and visit:
   http://127.0.0.1:8080
6. Optional health check in another browser tab:
   http://127.0.0.1:8080/health
   It should report ok=true and api_key_configured=true.

Keep your API key private. Never commit it to GitHub.

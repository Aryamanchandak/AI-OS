# gateway.py  (the operator runs this)
import os
os.environ.setdefault("GEMINI_API_KEY_1", "AIza...loaded-at-startup")
os.environ.setdefault("GITHUB_ACCESS_TOKEN", "ghp_...loaded-at-startup")
import telegram_adapter                      # runs in the SAME process
telegram_adapter.handle_message("hi there")
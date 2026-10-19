# DecisionRoom backend launcher. Run from anywhere:  .\start_backend.ps1
#
# Why not a plain `python -m uvicorn --reload`: uvicorn's watcher recurses into
# .venv, and torch/pandas/openai fire .py-change events on Windows whenever their
# caches update at import time. Every such event restarted the server mid-request
# (random "Failed to fetch", uploads/evaluations killed between steps). Excluding
# .venv scopes the watcher to project code only.
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn api:app `
    --host 127.0.0.1 --port 8000 `
    --reload --reload-exclude "$PSScriptRoot\.venv"

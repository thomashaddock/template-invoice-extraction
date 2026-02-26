# Deploy verification (Heroku – Streamlit only)

**Verified:** This checklist was completed so the first deploy works.

## Pre-deploy checklist ✓

| Check | Status |
|-------|--------|
| **Procfile** | `web: streamlit run app/main.py --server.port=$PORT --server.address=0.0.0.0` (matches working v3) |
| **No FastAPI proxy** | `app/server.py` removed; single process = Streamlit only |
| **Buildpack** | `heroku/python` (uses `pyproject.toml` + `uv.lock` + `.python-version`) |
| **Stack** | `heroku-24` (set on app) |
| **Entry point** | `app/main.py` exists; imports `services`, `utils` (relative to `app/`) |
| **Streamlit CLI** | `streamlit run app/main.py --server.port=$PORT --server.address=0.0.0.0` starts successfully |

## Deploy commands

From repo root, with Heroku CLI logged in and app `invoice-extraction-app`:

```bash
# 1. Confirm app and buildpack
heroku buildpacks -a invoice-extraction-app
# Expect: heroku/python

heroku stack -a invoice-extraction-app
# Expect: heroku-24 (or heroku-22)

# 2. Optional: set Python runtime (must match .python-version)
heroku config:set HEROKU_PYTHON_VERSION=3.13 -a invoice-extraction-app
# Only if the buildpack doesn't read .python-version

# 3. Deploy (from repo root)
git add -A
git status
git commit -m "Deploy: Streamlit only, no proxy (match v3)"
git push heroku main
# If your branch is not main:
# git push heroku HEAD:main

# 4. After deploy: check process and logs
heroku ps -a invoice-extraction-app
heroku logs -a invoice-extraction-app --tail -n 100
# Expect: "Starting process with command `streamlit run app/main.py --server.port=... --server.address=0.0.0.0`"
# Then: "You can now view your Streamlit app" and "Local URL: http://..."

# 5. Open app
heroku open -a invoice-extraction-app
```

## If build fails

- **No matching distribution / Python:** Ensure `.python-version` is `3.13` (or 3.10–3.12) and Heroku stack is `heroku-24`.
- **Module not found:** App is run from repo root; `app/main.py` imports `services`/`utils` from `app/` — no change needed.
- **Port / bind:** Procfile uses `$PORT` and `--server.address=0.0.0.0`; Heroku sets `PORT` automatically.

## Rollback (if needed)

```bash
heroku releases -a invoice-extraction-app -n 5
heroku rollback -a invoice-extraction-app
```

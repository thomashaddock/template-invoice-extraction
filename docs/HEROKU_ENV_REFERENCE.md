# Heroku config vars reference (invoice-extraction-app)

This checklist is for the **Streamlit + FastAPI proxy** deployment. Values are not stored here; use `heroku config -a invoice-extraction-app` to view.

## Required by the app (all present on Heroku ✓)

| Config var | Used by | Purpose |
|------------|---------|--------|
| `CREWAI_ENTERPRISE_API_URL` | `app/clients/crewai.py` | CrewAI Enterprise API base URL for kickoff/status. |
| `CREWAI_ENTERPRISE_BEARER_TOKEN` | `app/clients/crewai.py` | Bearer token for CrewAI Enterprise API. |
| `GOOGLE_DRIVE_FOLDER_ID` | `app/clients/gdrive.py` | Drive folder ID for uploads. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `app/clients/gdrive.py`, flow in `src/doc2data/main.py` | Service account JSON (file path or raw JSON string). |

## Set automatically by Heroku

| Config var | Used by | Purpose |
|------------|---------|--------|
| `PORT` | `app/server.py` | Web process must bind to this port. Heroku sets it. |

## Optional (not required for Streamlit to load)

| Config var | Used by | Notes |
|------------|---------|--------|
| `WEBHOOK_BEARER_TOKEN` | `app/webhook_server.py` | Only if using webhook callbacks; currently using polling. |
| `WEBHOOK_RESULTS_DIR` | `app/webhook_server.py` | Defaults to `/tmp/doc2data_webhooks` if unset. |
| `CREWAI_WEBHOOK_URL` | `app/clients/crewai.py` | Commented out; webhooks disabled. |
| `DATABASE_URL` | `src/doc2data/tools/db_writer.py` | DB write step is commented out in the flow. |

## Not needed on Heroku (CrewAI Enterprise runs the flow)

- `OPENAI_API_KEY`, `GROQ_API_KEY` — used by the flow when it runs on **CrewAI Enterprise**, not in the Heroku process.

## Verification

All four required vars are set on `invoice-extraction-app`. If the Streamlit UI is still broken, the cause is likely not missing env (e.g. WebSocket/proxy or Python path), not config vars.

# invoice_extraction — Invoice Extraction with CrewAI

Extract structured data from PDF invoices using a [CrewAI](https://crewai.com) flow: PDF text extraction, invoice validation, and structured field extraction (vendor, dates, line items, totals).

## Quick start (clone → run)

### 1. Clone and install

```bash
git clone https://github.com/crewai/template_invoice_extraction.git
cd template_invoice_extraction
pip install uv
uv sync
```

Requires Python ≥3.10,<3.14.

### 2. Create resources and set env

You need:

| Resource | Used by | What to do |
|----------|--------|------------|
| **CrewAI Enterprise** | Flow + app | Sign up at [CrewAI](https://crewai.com). Deploy this repo’s flow (see below). Copy the automation’s API URL and bearer token. |
| **OpenAI API key** | Flow (LLM) | [platform.openai.com](https://platform.openai.com/api-keys) → create key. |
| **Groq API key** | Flow (LLM) | [console.groq.com](https://console.groq.com) → create key. |
| **Google Drive** | Flow + app | Create a Google Cloud project, enable Drive API, create a service account, download JSON key. Create a Drive folder and share it with the service account email. Use folder ID in `GOOGLE_DRIVE_FOLDER_ID`. |

Env is split by deployment target:

- **Crew (flow):** `src/.env.example` → copy to `src/.env` (or set in the AMP dashboard when you deploy). Used for `crewai run` and when CrewAI Enterprise runs the flow.
- **App (frontend):** `app/.env.example` → for local run, copy to `.env` in the **project root** (the app’s `load_dotenv()` reads from there). For Heroku, set the same vars as config vars.

Fill in your keys and IDs in the relevant `.env`; never commit `.env`.

### 3. Deploy the flow to CrewAI Enterprise

The Streamlit app calls your flow via the CrewAI Enterprise API. Deploy the flow first:

```bash
crewai login
crewai deploy create
```

Use the AMP dashboard to configure env (or use `src/.env`); get **CREWAI_ENTERPRISE_API_URL** and **CREWAI_ENTERPRISE_BEARER_TOKEN** for the app. See [Deploy to AMP](https://docs.crewai.com/en/enterprise/guides/deploy-crew) for details.

### 4. Run the app locally

```bash
streamlit run app/main.py
```

Upload or pick a sample PDF, click “Run Crew,” and view extracted invoice data.

### 5. (Optional) Deploy the app to Heroku or similar

To run the demo in the cloud:

1. **Set config vars** (same names as in `app/.env.example`):

   ```bash
   heroku create your-app-name
   heroku config:set CREWAI_ENTERPRISE_API_URL=https://...
   heroku config:set CREWAI_ENTERPRISE_BEARER_TOKEN=...
   heroku config:set GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
   heroku config:set GOOGLE_DRIVE_FOLDER_ID=...
   ```

2. **Deploy:**

   ```bash
   git push heroku main
   ```

   Heroku’s Python buildpack uses **uv** (`pyproject.toml` + `uv.lock`); no `requirements.txt` is needed. The `Procfile` runs: `streamlit run app/main.py --server.port=$PORT --server.address=0.0.0.0`. Use `runtime.txt` in the repo to pin the Python version (e.g. 3.11).

Other platforms (Railway, Render, etc.): use the same env vars and process; if they don’t support uv, generate `requirements.txt` with `uv export --no-dev -o requirements.txt`.

---

## Project structure

- **`src/`** — CrewAI flow and crew
  - `.env.example` — Env template for **Crew deployment** (flow); copy to `src/.env` or set in AMP
  - `invoice_extraction/` — `main.py` (InvoiceProcessingFlow), `crews/extraction_crew/`, `tools/`, `models.py`
- **`app/`** — Streamlit demo (frontend)
  - `.env.example` — Env template for **Heroku / local app**; copy to project root `.env` for local run, or set Heroku config vars
  - `main.py` — Upload or pick sample PDF, trigger flow, show results
  - `clients/` — CrewAI Enterprise API, Google Drive
  - `services/` — Execution lifecycle (upload, kickoff, poll status)
  - `public/samples/` — Sample PDF invoices

## Running the flow (CrewAI Enterprise)

From the project root:

```bash
crewai run
```

This runs the invoice_extraction flow as defined in `pyproject.toml` (CrewAI type: flow).

### Local CLI runs (no Streamlit)

- **Local PDF (no Drive):**  
  `uv run run_local [path/to/invoice.pdf]`  
  Defaults to the first PDF in `app/public/samples/` if no path is given.

- **Simulate Drive trigger:**  
  `uv run run_gdrive <drive_file_id> [source_filename]`  
  Requires `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID` in `.env`.

- **Trigger with JSON payload:**  
  `uv run run_with_trigger '{"payload": {"drive_file_id": "...", "source_filename": "..."}}'`

## Configuration

- **Agents and tasks:** `src/invoice_extraction/crews/extraction_crew/config/agents.yaml` and `tasks.yaml`
- **Flow logic and tools:** `src/invoice_extraction/main.py` and `src/invoice_extraction/crews/extraction_crew/extraction_crew.py`
- **Env:** `src/.env.example` is the template for the CrewAI flow (Crew deployment). `app/.env.example` is the template for the Streamlit app (Heroku / frontend).

## Support

- [CrewAI documentation](https://docs.crewai.com)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
- [CrewAI Discord](https://discord.com/invite/X4JWnZnxPb)

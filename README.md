# doc2data — Invoice Extraction with CrewAI

Extract structured data from PDF invoices using a [CrewAI](https://crewai.com) flow: PDF text extraction, invoice validation, and structured field extraction (vendor, dates, line items, totals).

## Project structure

- **`src/doc2data/`** — CrewAI flow and crew
  - `main.py` — `InvoiceProcessingFlow` (Drive/Gmail trigger, extract → validate → extract fields)
  - `crews/extraction_crew/` — Extraction crew (agents + tasks YAML)
  - `tools/` — `InvoiceExtractorTool` (PDF text), optional `DBWriterTool`
  - `models.py` — Pydantic models for flow state and outputs
- **`app/`** — Streamlit demo
  - `main.py` — Upload or pick sample PDF, trigger flow, show results
  - `clients/` — CrewAI Enterprise API, Google Drive
  - `services/` — Execution lifecycle (upload, kickoff, poll status)
  - `public/samples/` — Sample PDF invoices

## Installation

Requires Python ≥3.10,<3.14. This project uses [uv](https://docs.astral.sh/uv/) for dependencies.

```bash
pip install uv
cd /path/to/template_invoice_extraction
uv sync
```

Copy environment variables and set required keys:

```bash
cp .env.example .env
# Edit .env: OPENAI_API_KEY, GROQ_API_KEY; for the app, CREWAI_ENTERPRISE_API_URL and CREWAI_ENTERPRISE_BEARER_TOKEN
```

See `.env.example` for all optional and required variables. **Do not commit `.env`.**

## Running the flow (CrewAI Enterprise)

From the project root:

```bash
crewai run
```

This runs the doc2data flow as defined in `pyproject.toml` (CrewAI type: flow).

### Local CLI runs

- **Local PDF (no Drive):**  
  `uv run run_local [path/to/invoice.pdf]`  
  Defaults to the first PDF in `app/public/samples/` if no path is given.

- **Simulate Drive trigger:**  
  `uv run run_gdrive <drive_file_id> [source_filename]`  
  Requires `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID` in `.env`.

- **Trigger with JSON payload:**  
  `uv run run_with_trigger '{"payload": {"drive_file_id": "...", "source_filename": "..."}}'`

## Running the Streamlit app

From the project root:

```bash
streamlit run app/main.py
```

The app uploads the selected PDF to Google Drive, kicks off the flow via CrewAI Enterprise, and polls for results. Configure `CREWAI_ENTERPRISE_API_URL`, `CREWAI_ENTERPRISE_BEARER_TOKEN`, and Google Drive in `.env` (or Heroku config vars if deployed).

## Configuration

- **Agents and tasks:** `src/doc2data/crews/extraction_crew/config/agents.yaml` and `tasks.yaml`
- **Flow logic and tools:** `src/doc2data/main.py` and `src/doc2data/crews/extraction_crew/extraction_crew.py`

## Support

- [CrewAI documentation](https://docs.crewai.com)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
- [CrewAI Discord](https://discord.com/invite/X4JWnZnxPb)

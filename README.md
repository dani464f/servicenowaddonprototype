# ServiceNow ITAM Right-Sizing Add-on (MVP Scaffold)

This repository now includes a runnable FastAPI scaffold implementing the MVP API surface from the technical blueprint:

- Telemetry ingestion (`/api/v1/ingestion/telemetry-batch`)
- Capability snapshot ingestion (`/api/v1/ingestion/capability-snapshots`)
- Policy CRUD + simulation
- Recommendation list/detail + approve/override actions
- Baseline scoring formulas and recommendation classification/action logic

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```

## Notes

- Storage is in-memory for scaffold purposes.
- This is intentionally not production code; it provides implementation-ready interfaces and baseline rule execution behavior.

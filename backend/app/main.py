from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .models import RunCreateRequest
from .pipeline import TwoShotPipeline
from .services.seeds import SeedService
from .storage import Storage

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "prospects.db"
PARENT_SEED_PATH = ROOT / "app" / "seeds" / "parent_seeds.yaml"
EXPANSION_SEED_PATH = ROOT / "app" / "seeds" / "expansion_seeds.yaml"

app = FastAPI(title="Collegiate Prospecting API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage(DB_PATH)
seed_service = SeedService(PARENT_SEED_PATH, EXPANSION_SEED_PATH)
pipeline = TwoShotPipeline(
    storage=storage,
    parent_seed_file=PARENT_SEED_PATH,
    expansion_seed_file=EXPANSION_SEED_PATH,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/runs")
def list_runs() -> list[dict]:
    return [run.model_dump() for run in storage.list_runs()]


@app.get("/seeds")
def list_seeds() -> dict:
    return seed_service.load_bundle().model_dump()


@app.post("/runs")
def create_run(payload: RunCreateRequest) -> dict:
    run_id = storage.create_run(
        payload.run_name, notes=payload.notes, run_mode=payload.mode
    )
    stats = pipeline.run(run_id, mode=payload.mode, seed_ids=payload.normalized_seed_ids)
    run = next((r for r in storage.list_runs() if r.run_id == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found after creation.")
    result = run.model_dump()
    result["stats"] = stats
    return result


@app.get("/runs/{run_id}/records")
def run_records(run_id: int) -> list[dict]:
    return [record.to_csv_row() for record in storage.list_records(run_id)]


@app.get("/runs/{run_id}/records/detail")
def run_record_details(run_id: int) -> list[dict]:
    return storage.list_record_details(run_id)


@app.get("/runs/{run_id}/logs")
def run_logs(run_id: int) -> list[dict]:
    return storage.list_run_logs(run_id)


@app.get("/runs/{run_id}/diagnostics")
def run_diagnostics(run_id: int) -> dict:
    return storage.get_run_diagnostics(run_id)


@app.get("/runs/{run_id}/export")
def export_run(run_id: int) -> FileResponse:
    csv_path = DATA_DIR / "exports" / f"run_{run_id}.csv"
    out = storage.export_csv(run_id, csv_path)
    if not out.exists():
        raise HTTPException(status_code=404, detail="CSV export failed.")
    return FileResponse(
        path=out,
        media_type="text/csv",
        filename=out.name,
    )

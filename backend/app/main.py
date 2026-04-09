from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .models import RunCreateRequest
from .pipeline import TwoShotPipeline
from .storage import Storage

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "prospects.db"
SEED_PATH = ROOT / "app" / "seeds" / "default_seed_categories.yaml"

app = FastAPI(title="Collegiate Prospecting API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage(DB_PATH)
pipeline = TwoShotPipeline(storage=storage, seed_file=SEED_PATH)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/runs")
def list_runs() -> list[dict]:
    return [run.model_dump() for run in storage.list_runs()]


@app.post("/runs")
def create_run(payload: RunCreateRequest) -> dict:
    run_id = storage.create_run(payload.run_name, notes=payload.notes)
    stats = pipeline.run(run_id)
    run = next((r for r in storage.list_runs() if r.run_id == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found after creation.")
    result = run.model_dump()
    result["stats"] = stats
    return result


@app.get("/runs/{run_id}/records")
def run_records(run_id: int) -> list[dict]:
    return [record.to_csv_row() for record in storage.list_records(run_id)]


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

"""
api/main.py — RCA Agent FastAPI Backend

Endpoints:
  POST /analyze              — run full RCA, returns JSON result
  GET  /analyze/stream       — SSE stream of agent steps + final report
  POST /analyze/upload       — upload a log file and run RCA
  GET  /reports              — list all saved RCA reports
  GET  /reports/{report_id}  — fetch a single saved report
  DELETE /reports/{report_id} — delete a saved report

Run:
  uvicorn patchly_rca.api.main:app --reload --port 8000
"""

import os
import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
from pydantic import BaseModel

from patchly_rca.agent import run_rca
from patchly_rca.config import RCA

app = FastAPI(
    title="Patchly RCA Agent",
    description="AI-powered Root Cause Analysis for production incidents",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_OUTPUT_DIR = RCA.get("output_dir", "/tmp/rca_reports")


# ── Request / Response models ─────────────────────────────────

class AnalyzeRequest(BaseModel):
    input: str
    source: str | None = None


class AnalyzeResponse(BaseModel):
    rca_report:   str
    steps_taken:  int
    provider:     str
    report_saved: str
    timestamp:    str


class ReportMeta(BaseModel):
    report_id:  str
    filename:   str
    created_at: str
    size_bytes: int


# ── Helpers ───────────────────────────────────────────────────

def _list_reports() -> list[ReportMeta]:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    reports = []
    for fname in sorted(os.listdir(_OUTPUT_DIR), reverse=True):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(_OUTPUT_DIR, fname)
        stat  = os.stat(fpath)
        reports.append(ReportMeta(
            report_id  = fname.replace(".txt", ""),
            filename   = fname,
            created_at = datetime.fromtimestamp(stat.st_ctime).isoformat(),
            size_bytes = stat.st_size,
        ))
    return reports


def _read_report(report_id: str) -> str:
    path = os.path.join(_OUTPUT_DIR, f"{report_id}.txt")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    with open(path) as f:
        return f.read()


# ── Endpoints ─────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Run a full RCA investigation and return the structured report."""
    try:
        result = run_rca(req.input, source_override=req.source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AnalyzeResponse(
        rca_report   = result["rca_report"],
        steps_taken  = result["steps_taken"],
        provider     = result["provider"],
        report_saved = result.get("report_saved", ""),
        timestamp    = datetime.utcnow().isoformat(),
    )


@app.get("/analyze/stream")
async def analyze_stream(input: str, source: str | None = None):
    """
    SSE stream — emits agent steps as they happen, then the final report.
    Connect with EventSource in JS or httpx in Python.
    """
    async def _event_generator() -> AsyncGenerator[str, None]:
        yield _sse("status", {"message": "Investigation started..."})

        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_rca(input, source_override=source)
        )

        yield _sse("steps", {"steps_taken": result["steps_taken"], "provider": result["provider"]})
        yield _sse("report", {"rca_report": result["rca_report"], "report_saved": result.get("report_saved", "")})
        yield _sse("done", {"message": "Investigation complete"})

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@app.post("/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(file: UploadFile = File(...)):
    """Upload a log file and run RCA against it."""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    tmp_path = os.path.join(_OUTPUT_DIR, f"upload_{file.filename}")
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        result = run_rca(tmp_path, source_override="log_file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return AnalyzeResponse(
        rca_report   = result["rca_report"],
        steps_taken  = result["steps_taken"],
        provider     = result["provider"],
        report_saved = result.get("report_saved", ""),
        timestamp    = datetime.utcnow().isoformat(),
    )


@app.get("/reports", response_model=list[ReportMeta])
def list_reports():
    """List all saved RCA reports."""
    return _list_reports()


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    """Fetch the full text of a saved RCA report."""
    return {"report_id": report_id, "content": _read_report(report_id)}


@app.delete("/reports/{report_id}")
def delete_report(report_id: str):
    """Delete a saved RCA report."""
    path = os.path.join(_OUTPUT_DIR, f"{report_id}.txt")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
    os.remove(path)
    return {"deleted": report_id}


# ── SSE helper ────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

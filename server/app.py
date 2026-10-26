"""Breadcrumbs local server: serves the web app and runs analyses on photos the
user uploads. Photos are processed in memory and never written to disk."""

from __future__ import annotations

import io
import os
import threading
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
import torch

from .engine import Engine, Photo, analyze, blur_regions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
MAX_PHOTOS = 24

app = FastAPI(title="Breadcrumbs")
_engine: Engine | None = None
_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def engine() -> Engine:
    global _engine
    with _lock, torch.no_grad():
        if _engine is None:
            _engine = Engine()
    return _engine


def _load(data: bytes, name: str) -> Photo:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((1280, 1280))
    # strip everything but pixels: GPS EXIF must not be what gives the answer away
    clean = Image.new("RGB", img.size)
    clean.paste(img)
    return Photo(name=name, image=clean)


def _run(job_id: str, photos: list[Photo], home, target_km: float):
    job = _jobs[job_id]
    try:
        def progress(done, total):
            job["progress"] = round(done / total * 0.8, 3)
        with torch.no_grad():  # grad mode is per-thread; this runs in a worker thread
            result = analyze(engine(), photos, home=home, target_km=target_km, progress=progress)
        job["photos"] = photos
        job["result"] = result
        job["progress"] = 1.0
        job["status"] = "done"
    except Exception as exc:  # surface the failure to the UI instead of hanging
        job["status"] = "error"
        job["error"] = str(exc)


@app.post("/api/analyze")
async def start(files: list[UploadFile] = File(...), home_lat: float | None = Form(None),
                home_lon: float | None = Form(None), target_km: float = Form(5.0)):
    if not 2 <= len(files) <= MAX_PHOTOS:
        raise HTTPException(400, f"Upload between 2 and {MAX_PHOTOS} photos.")
    photos = []
    for f in files:
        try:
            photos.append(_load(await f.read(), f.filename or "photo.jpg"))
        except Exception:
            raise HTTPException(400, f"Couldn't read {f.filename} as an image.")
    home = (home_lat, home_lon) if home_lat is not None and home_lon is not None else None
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {"status": "running", "progress": 0.0}
    threading.Thread(target=_run, args=(job_id, photos, home, target_km), daemon=True).start()
    return {"job": job_id}


@app.get("/api/jobs/{job_id}")
def status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    out = {"status": job["status"], "progress": job.get("progress", 0)}
    if job["status"] == "done":
        out["result"] = job["result"]
    if job["status"] == "error":
        out["error"] = job["error"]
    return JSONResponse(out)


@app.get("/api/jobs/{job_id}/photo/{i}")
def photo(job_id: str, i: int, fixed: int = 0):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done" or not 0 <= i < len(job["photos"]):
        raise HTTPException(404)
    img = job["photos"][i].image
    if fixed:
        regions = job["result"]["plan"]["blurred"].get(str(i), [])
        img = blur_regions(img, regions)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    from fastapi.responses import Response
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.get("/api/health")
def health():
    return {"ok": True, "model_loaded": _engine is not None}


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


app.mount("/", StaticFiles(directory=WEB), name="web")

"""FastAPI backend for the retention dashboard.

Run: uvicorn churnlab.api:app --port 8000   then open http://localhost:8000
"""
from __future__ import annotations

import json
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import messages
from .config import OFFER_KEYS, RESULTS_DIR, ROOT
from .data import load

app = FastAPI(title="Telecom Churn & Retention", version="1.0.0")
WEB = ROOT / "web"
DATASETS = ["overview", "customers", "retention", "messages_eval"]


@lru_cache(maxsize=None)
def _load(name):
    path = RESULTS_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, f"{name} missing - run `python -m churnlab.pipeline` first")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _raw():
    return load().set_index("customerID")


@app.get("/api/health")
def health():
    return {"status": "ok", "datasets": [d for d in DATASETS if (RESULTS_DIR / f"{d}.json").exists()]}


@app.get("/api/{name}")
def dataset(name: str):
    if name not in DATASETS:
        raise HTTPException(404, "unknown dataset")
    return _load(name)


@app.get("/api/customer/{customer_id}")
def customer(customer_id: str):
    for c in _load("customers"):
        if c["id"] == customer_id:
            return c
    raise HTTPException(404, "customer not found or not active")


class MessageRequest(BaseModel):
    customer_id: str
    offer: str
    lang: str = Field("en", pattern="^(en|fr)$")
    use_llm: bool = True


@app.post("/api/message")
def message(req: MessageRequest):
    if req.offer not in OFFER_KEYS:
        raise HTTPException(400, "unknown offer")
    if req.customer_id not in _raw().index:
        raise HTTPException(404, "customer not found")
    c = _raw().loc[req.customer_id].to_dict()
    return messages.generate(c, req.offer, req.lang, use_llm=req.use_llm)


class ValidateRequest(BaseModel):
    customer_id: str
    offer: str
    lang: str = Field("en", pattern="^(en|fr)$")
    text: str = Field(..., min_length=1, max_length=3000)


@app.post("/api/validate")
def validate(req: ValidateRequest):
    if req.offer not in OFFER_KEYS or req.customer_id not in _raw().index:
        raise HTTPException(400, "unknown customer or offer")
    f = messages.facts(_raw().loc[req.customer_id].to_dict(), req.offer)
    problems = messages.validate(req.text, f, req.lang)
    return {"ok": not problems, "problems": problems}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")

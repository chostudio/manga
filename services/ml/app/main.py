"""
ML inference microservice (FastAPI).

The Python half of the manga pipeline: the only part that *must* be Python
(ultralytics YOLO, dghs-imgutils detectors + WD tagger, OpenCLIP/torch). It is
stateless — models load once per worker and it holds no database. The Java
services (ingestion, api) call it over HTTP.

Endpoints:
  GET  /health         liveness
  POST /split-panels   full page image -> panel crops (PNG, base64) in reading order
  POST /index-panel    one panel image -> {embedding, tags, tag_sources, sub_elements}
  POST /embed-text     {"text": ...} -> {embedding} (CLIP text vector for search)

Images are posted as multipart form files (field name "image"); base64 out keeps
the contract simple for the Java clients.
"""
from __future__ import annotations

import base64

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

from app.embedding import generate_text_embedding
from app.image_split import split_image_into_panels
from app.indexing import index_panel

app = FastAPI(title="manga-ml", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/split-panels")
async def split_panels(image: UploadFile = File(...)) -> dict:
    """Detect + crop panels from a full page. Returns PNG crops (base64), in order."""
    data = await image.read()
    panels = split_image_into_panels(data)
    return {
        "panel_count": len(panels),
        "panels": [
            {"index": i, "image_b64": base64.b64encode(p).decode("ascii")}
            for i, p in enumerate(panels)
        ],
    }


@app.post("/index-panel")
async def index_panel_endpoint(image: UploadFile = File(...)) -> dict:
    """Detect sub-elements, per-region booru-tag, and embed one panel crop."""
    data = await image.read()
    return index_panel(data)


class EmbedTextRequest(BaseModel):
    text: str


@app.post("/embed-text")
def embed_text(req: EmbedTextRequest) -> dict:
    """CLIP text embedding for the search vibes fallback."""
    return {"embedding": generate_text_embedding(req.text) or None}

# ml — ML inference service (Python / FastAPI)

The Python half of the manga pipeline: panel detection (YOLO), sub-element
detection (anime face/eyes/hand/person via `dghs-imgutils`), booru tagging (WD
EVA02-Large), and OpenCLIP embeddings. It exists because this stack has no Java
equivalent. Stateless — no database; models load once per worker.

## Endpoints
| Method | Path | In | Out |
|---|---|---|---|
| GET | `/health` | — | `{status}` |
| POST | `/split-panels` | multipart `image` (full page) | `{panel_count, panels:[{index, image_b64}]}` |
| POST | `/index-panel` | multipart `image` (one panel) | `{embedding, tags, tag_sources, sub_elements}` |
| POST | `/embed-text` | `{text}` | `{embedding}` |

## Run locally
```bash
cd services/ml
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
# first call downloads model weights to ~/.cache/huggingface
```

## Config (env)
- `WD_TAGGER_MODEL` (default `EVA02_Large`) — WD tagger; `SwinV2_v3` is faster.
- `WD_TAG_THRESHOLD` (default `0.30`) — general-tag confidence floor.

## Notes
- Reuses the exact detection/tagging/embedding logic from the original Django
  monolith (`backend/api/{detectors,tagging,embedding,image_split}.py`), with
  Django-specific bits removed (settings → env). The DB writes that were in
  `ingest.index_panel` now live in the Java ingestion service; this service
  returns the computed values as JSON instead.

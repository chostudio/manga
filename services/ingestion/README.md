# ingestion — MangaDex ingest / orchestration (Java / Spring Boot)

Downloads MangaDex chapters and orchestrates indexing: for each page it calls the
Python `ml` service to split panels and to detect/tag/embed each panel, then
writes `StoredPanel`/`PanelTag`/`PanelSubElement` rows to the shared Postgres and
panel images to storage. Ports the monolith's `mangadex.py` + ingest pipeline.

## Endpoints
- `POST /ingest` `{ "url": "<mangadex chapter url>", "quality": "data|data-saver" }`
  → `202 { job_id, state, log, summary }` (async job)
- `GET /ingest/{jobId}` → job status + progress log

## Run locally
```bash
cd services/ingestion
./gradlew bootRun          # needs Postgres on :5432 and ml on :8001
curl -X POST localhost:8090/ingest -H 'content-type: application/json' \
  -d '{"url":"https://mangadex.org/chapter/<uuid>","quality":"data-saver"}'
```

## Config (env)
- `DATABASE_JDBC_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `ML_BASE_URL` (default `http://localhost:8001`)
- `MANGA_STORAGE_LOCAL_DIR` (default `../../backend/media/storage`), `MEDIA_URL`
- `INGESTION_PORT` (default `8090`)

## Notes
- Idempotent: upserts on `(chapter,page,panel)` and `(panel,tag)`, and prunes
  panels that a re-ingest no longer produces.
- Async jobs are in-memory today; the `JobService` is the seam where a RabbitMQ
  queue + workers would slot in for horizontal scaling.
- Direct file uploads (the old `/upload`) aren't ported — the MangaDex flow is the
  primary path; add a `/upload` endpoint here if needed.

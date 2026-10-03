# api — search / BFF service (Java / Spring Boot)

The Angular-facing query service. Owns tag-first hybrid **search** ranking; calls
the Python `ml` service only for the CLIP text vector (vibes fallback). Reads the
shared Postgres directly (JdbcTemplate + native pgvector SQL).

## Endpoint
`GET /search?q=<text>` → `{ "panels": [ { id, chapter_id, page_index, panel_index,
url, matched_via, score, similarity, matched_tags, matched_labels, tags } ] }`
(same JSON shape the Angular frontend already consumes.)

Ranking is a direct port of the monolith's search view (see `QueryExpander` for the
emotion synonym map + matcher, `SearchService` for the blend).

## Run locally
```bash
cd services/api
./gradlew bootRun          # needs Postgres on :5432 and ml on :8001
# GET http://localhost:8080/search?q=angry
```

## Config (env)
- `DATABASE_JDBC_URL` (default `jdbc:postgresql://localhost:5432/manga`)
- `POSTGRES_USER` / `POSTGRES_PASSWORD` (default `postgres` / `postgrespassword`)
- `ML_BASE_URL` (default `http://localhost:8001`)
- `API_PORT` (default `8080`), `CORS_ORIGINS`

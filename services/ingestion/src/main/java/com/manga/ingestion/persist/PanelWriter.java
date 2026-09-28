package com.manga.ingestion.persist;

import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.manga.ingestion.ml.MlClient;

/**
 * Writes ingest results into the shared Postgres (Django-created tables), using
 * INSERT ... ON CONFLICT upserts so re-ingesting a chapter overwrites rather than
 * duplicates. Vector and jsonb columns are passed as ::vector / ::jsonb literals.
 */
@Repository
public class PanelWriter {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public PanelWriter(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    /** Upsert the chapter row; returns its bigint PK. */
    public long upsertChapter(String chapterId, String quality, int pageCount) {
        return jdbc.queryForObject(
                "INSERT INTO api_chapteringestion (chapter_id, quality, page_count, created_at, updated_at) "
                        + "VALUES (?, ?, ?, now(), now()) "
                        + "ON CONFLICT (chapter_id, quality) DO UPDATE SET page_count = EXCLUDED.page_count, "
                        + "updated_at = now() RETURNING id",
                Long.class, chapterId, quality, pageCount);
    }

    /** Upsert a panel row; returns its bigint PK. */
    public long upsertPanel(long chapterPk, int pageIndex, int panelIndex, String storageKey,
                            long byteSize, String contentType, String publicUrl,
                            float[] embedding, Map<String, Double> tags) {
        String embLiteral = embedding == null ? null : toVectorLiteral(embedding);
        String tagsJson = (tags == null || tags.isEmpty()) ? null : toJson(tags);
        return jdbc.queryForObject(
                "INSERT INTO api_storedpanel "
                        + "(chapter_id, page_index, panel_index, storage_key, byte_size, content_type, "
                        + " public_url, embedding, tags, created_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS vector), CAST(? AS jsonb), now()) "
                        + "ON CONFLICT (chapter_id, page_index, panel_index) DO UPDATE SET "
                        + "storage_key = EXCLUDED.storage_key, byte_size = EXCLUDED.byte_size, "
                        + "content_type = EXCLUDED.content_type, public_url = EXCLUDED.public_url, "
                        + "embedding = EXCLUDED.embedding, tags = EXCLUDED.tags RETURNING id",
                Long.class,
                chapterPk, pageIndex, panelIndex, storageKey, byteSize, contentType, publicUrl,
                embLiteral, tagsJson);
    }

    /** Replace all derived rows (tags + sub-elements) for a panel, idempotently. */
    @Transactional
    public void writeDerived(long panelId, Map<String, Double> tags, Map<String, String> sources,
                             List<MlClient.SubElement> subs) {
        jdbc.update("DELETE FROM api_paneltag WHERE panel_id = ?", panelId);
        jdbc.update("DELETE FROM api_panelsubelement WHERE panel_id = ?", panelId);

        if (tags != null && !tags.isEmpty()) {
            List<Map.Entry<String, Double>> entries = List.copyOf(tags.entrySet());
            jdbc.batchUpdate(
                    "INSERT INTO api_paneltag (panel_id, tag, score, source) VALUES (?, ?, ?, ?)",
                    entries, entries.size(),
                    (ps, e) -> {
                        ps.setLong(1, panelId);
                        ps.setString(2, e.getKey());
                        ps.setDouble(3, e.getValue());
                        ps.setString(4, sources.getOrDefault(e.getKey(), "panel"));
                    });
        }
        if (subs != null && !subs.isEmpty()) {
            jdbc.batchUpdate(
                    "INSERT INTO api_panelsubelement (panel_id, label, bbox, embedding, created_at) "
                            + "VALUES (?, ?, CAST(? AS jsonb), NULL, now())",
                    subs, subs.size(),
                    (ps, s) -> {
                        ps.setLong(1, panelId);
                        ps.setString(2, s.label());
                        ps.setString(3, s.bbox() == null ? null : toJson(s.bbox()));
                    });
        }
    }

    /** Delete panels of a chapter whose (page,panel) is not in the freshly-ingested set. */
    public void pruneStale(long chapterPk, List<int[]> keep) {
        List<Long> staleIds = jdbc.query(
                "SELECT id, page_index, panel_index FROM api_storedpanel WHERE chapter_id = ?",
                (rs, i) -> {
                    long id = rs.getLong("id");
                    int pg = rs.getInt("page_index");
                    int pn = rs.getInt("panel_index");
                    boolean kept = keep.stream().anyMatch(k -> k[0] == pg && k[1] == pn);
                    return kept ? -1L : id;
                }, chapterPk).stream().filter(id -> id >= 0).toList();
        for (Long id : staleIds) {
            jdbc.update("DELETE FROM api_storedpanel WHERE id = ?", id);
        }
    }

    private String toJson(Object o) {
        try {
            return mapper.writeValueAsString(o);
        } catch (Exception e) {
            return null;
        }
    }

    private static String toVectorLiteral(float[] v) {
        StringBuilder sb = new StringBuilder(v.length * 8).append('[');
        for (int i = 0; i < v.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(v[i]);
        }
        return sb.append(']').toString();
    }
}

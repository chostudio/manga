package com.manga.api.search;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Read access to the shared Postgres (Django-created tables). Vector similarity
 * uses native pgvector SQL (the query vector is passed as a string cast to
 * ::vector), which avoids a Hibernate custom-type for the vector column.
 */
@Repository
public class PanelRepository {

    private final NamedParameterJdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public PanelRepository(NamedParameterJdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public record TagRow(long panelId, String tag, double score) {}

    public record LabelRow(long panelId, String label) {}

    public record VecRow(long panelId, double similarity) {}

    public record PanelMeta(long id, String chapterId, int pageIndex, int panelIndex,
                            String url, Map<String, Double> tags) {}

    public List<String> distinctTags() {
        return jdbc.getJdbcTemplate().queryForList(
                "SELECT DISTINCT tag FROM api_paneltag", String.class);
    }

    public List<TagRow> tagRows(Collection<String> tags) {
        if (tags.isEmpty()) {
            return List.of();
        }
        return jdbc.query(
                "SELECT panel_id, tag, score FROM api_paneltag WHERE tag IN (:tags)",
                new MapSqlParameterSource("tags", tags),
                (rs, i) -> new TagRow(rs.getLong("panel_id"), rs.getString("tag"), rs.getDouble("score")));
    }

    public List<LabelRow> subElementPanels(Collection<String> labels) {
        if (labels.isEmpty()) {
            return List.of();
        }
        return jdbc.query(
                "SELECT DISTINCT panel_id, label FROM api_panelsubelement WHERE label IN (:labels)",
                new MapSqlParameterSource("labels", labels),
                (rs, i) -> new LabelRow(rs.getLong("panel_id"), rs.getString("label")));
    }

    public List<VecRow> vectorSearch(float[] embedding, int topK) {
        String vec = toVectorLiteral(embedding);
        MapSqlParameterSource p = new MapSqlParameterSource()
                .addValue("vec", vec)
                .addValue("k", topK);
        return jdbc.query(
                "SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS sim "
                        + "FROM api_storedpanel WHERE embedding IS NOT NULL "
                        + "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :k",
                p,
                (rs, i) -> new VecRow(rs.getLong("id"), rs.getDouble("sim")));
    }

    public Map<Long, PanelMeta> panelsByIds(Collection<Long> ids) {
        Map<Long, PanelMeta> out = new LinkedHashMap<>();
        if (ids.isEmpty()) {
            return out;
        }
        jdbc.query(
                "SELECT p.id, c.chapter_id AS chapter, p.page_index, p.panel_index, "
                        + "p.public_url, p.tags "
                        + "FROM api_storedpanel p "
                        + "JOIN api_chapteringestion c ON p.chapter_id = c.id "
                        + "WHERE p.id IN (:ids)",
                new MapSqlParameterSource("ids", ids),
                rs -> {
                    long id = rs.getLong("id");
                    out.put(id, new PanelMeta(
                            id,
                            rs.getString("chapter"),
                            rs.getInt("page_index"),
                            rs.getInt("panel_index"),
                            rs.getString("public_url"),
                            parseTags(rs.getString("tags"))));
                });
        return out;
    }

    private Map<String, Double> parseTags(String json) {
        if (json == null || json.isBlank()) {
            return Map.of();
        }
        try {
            return mapper.readValue(json, new TypeReference<Map<String, Double>>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }

    private static String toVectorLiteral(float[] v) {
        StringBuilder sb = new StringBuilder(v.length * 8);
        sb.append('[');
        for (int i = 0; i < v.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(v[i]);
        }
        sb.append(']');
        return sb.toString();
    }
}

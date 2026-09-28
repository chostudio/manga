package com.manga.api.search;

import java.util.List;

/** One panel returned by /search (JSON shape matches the old Django response). */
public record SearchResult(
        long id,
        String chapter_id,
        int page_index,
        int panel_index,
        String url,
        String matched_via,
        double score,
        double similarity,
        List<String> matched_tags,
        List<String> matched_labels,
        List<String> tags
) {}

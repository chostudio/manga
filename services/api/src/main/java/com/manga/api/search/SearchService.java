package com.manga.api.search;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

import com.manga.api.ml.MlClient;

/**
 * Tag-first hybrid ranking. Port of the Django search view:
 *   final = tag_score + LABEL_WEIGHT*#labels + VECTOR_WEIGHT*vibes
 * Strong (specific tag or detected sub-element) results outrank loose/vibes ones,
 * and vibes are returned only when nothing specific matched.
 */
@Service
public class SearchService {

    private static final int FINAL_K = 30;
    private static final int VECTOR_TOP_K = 60;
    private static final double LABEL_WEIGHT = 0.4;
    private static final double VECTOR_WEIGHT = 0.25;
    private static final int TAGS_IN_RESULT = 16;

    private final QueryExpander expander;
    private final PanelRepository repo;
    private final MlClient ml;

    public SearchService(QueryExpander expander, PanelRepository repo, MlClient ml) {
        this.expander = expander;
        this.repo = repo;
        this.ml = ml;
    }

    private static final class Acc {
        double tagScore;
        double specificScore;
        double vectorSim;
        final Set<String> labels = new HashSet<>();
        final Set<String> matchedTags = new HashSet<>();
    }

    public List<SearchResult> search(String query) {
        String q = query == null ? "" : query.strip();
        if (q.isEmpty()) {
            return List.of();
        }

        Map<Long, Acc> acc = new HashMap<>();

        // 1. tag matching
        Map<String, Double> candidates = expander.queryCandidates(q);
        Map<String, Double> matchedWeights =
                expander.matchStoredTags(candidates, repo.distinctTags());
        if (!matchedWeights.isEmpty()) {
            for (PanelRepository.TagRow row : repo.tagRows(matchedWeights.keySet())) {
                double w = matchedWeights.getOrDefault(row.tag(), 0.0);
                double contribution = row.score() * w;
                Acc a = acc.computeIfAbsent(row.panelId(), k -> new Acc());
                a.tagScore += contribution;
                a.matchedTags.add(row.tag());
                if (!expander.isLoose(row.tag())) {
                    a.specificScore += contribution;
                }
            }
        }

        // 2. sub-element label matching
        Set<String> wantedLabels = expander.queryLabels(q);
        if (!wantedLabels.isEmpty()) {
            for (PanelRepository.LabelRow row : repo.subElementPanels(wantedLabels)) {
                acc.computeIfAbsent(row.panelId(), k -> new Acc()).labels.add(row.label());
            }
        }

        // 3. vibes fallback (CLIP text vector from the ml service)
        float[] embedding = ml.embedText(q);
        if (embedding != null) {
            for (PanelRepository.VecRow row : repo.vectorSearch(embedding, VECTOR_TOP_K)) {
                acc.computeIfAbsent(row.panelId(), k -> new Acc()).vectorSim =
                        Math.max(0.0, row.similarity());
            }
        }

        if (acc.isEmpty()) {
            return List.of();
        }
        Map<Long, PanelRepository.PanelMeta> metas = repo.panelsByIds(acc.keySet());

        // 4. blend + split into strong / weak
        List<Scored> strong = new ArrayList<>();
        List<Scored> weak = new ArrayList<>();
        for (Map.Entry<Long, Acc> e : acc.entrySet()) {
            PanelRepository.PanelMeta meta = metas.get(e.getKey());
            if (meta == null) {
                continue;
            }
            Acc a = e.getValue();
            double finalScore = a.tagScore + LABEL_WEIGHT * a.labels.size() + VECTOR_WEIGHT * a.vectorSim;
            if (finalScore <= 0) {
                continue;
            }
            boolean isStrong = a.specificScore > 0 || !a.labels.isEmpty();
            (isStrong ? strong : weak).add(new Scored(finalScore, meta, a));
        }
        strong.sort(Comparator.comparingDouble((Scored s) -> s.finalScore).reversed());
        weak.sort(Comparator.comparingDouble((Scored s) -> s.finalScore).reversed());
        List<Scored> chosen = !strong.isEmpty() ? top(strong) : top(weak);

        // 5. build results
        List<SearchResult> results = new ArrayList<>(chosen.size());
        for (Scored s : chosen) {
            Acc a = s.acc;
            String matchedVia;
            if (a.specificScore > 0) {
                matchedVia = "tag";
            } else if (!a.labels.isEmpty()) {
                matchedVia = "sub_element";
            } else if (a.tagScore > 0) {
                matchedVia = "related";
            } else {
                matchedVia = "vibes";
            }
            List<String> matchedTags = new ArrayList<>(a.matchedTags);
            matchedTags.sort(Comparator
                    .comparingDouble((String t) -> matchedWeights.getOrDefault(t, 0.0)).reversed()
                    .thenComparing(Comparator.comparingDouble(
                            (String t) -> s.meta.tags().getOrDefault(t, 0.0)).reversed())
                    .thenComparing(Comparator.naturalOrder()));
            List<String> topTags = s.meta.tags().entrySet().stream()
                    .sorted(Map.Entry.<String, Double>comparingByValue().reversed())
                    .limit(TAGS_IN_RESULT)
                    .map(Map.Entry::getKey)
                    .toList();
            List<String> sortedLabels = new ArrayList<>(a.labels);
            sortedLabels.sort(Comparator.naturalOrder());

            results.add(new SearchResult(
                    s.meta.id(), s.meta.chapterId(), s.meta.pageIndex(), s.meta.panelIndex(),
                    s.meta.url(), matchedVia, round(s.finalScore), round(a.vectorSim),
                    matchedTags, sortedLabels, topTags));
        }
        return results;
    }

    private static List<Scored> top(List<Scored> list) {
        return list.size() > FINAL_K ? list.subList(0, FINAL_K) : list;
    }

    private static double round(double v) {
        return Math.round(v * 10000.0) / 10000.0;
    }

    private record Scored(double finalScore, PanelRepository.PanelMeta meta, Acc acc) {}
}

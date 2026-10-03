package com.manga.ingestion.ml;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

/** Client for the Python ml service (panel split + per-panel indexing). */
@Component
public class MlClient {

    private final RestClient ml;

    public MlClient(RestClient mlRestClient) {
        this.ml = mlRestClient;
    }

    public record SubElement(String label, Map<String, Object> bbox, double score) {}

    public record IndexResult(float[] embedding, Map<String, Double> tags,
                              Map<String, String> tagSources, List<SubElement> subElements) {}

    /** Split a full page into panel PNG crops (in reading order). */
    @SuppressWarnings("unchecked")
    public List<byte[]> splitPanels(byte[] pageBytes) {
        Map<String, Object> body = ml.post()
                .uri("/split-panels")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(imagePart(pageBytes, "page.jpg"))
                .retrieve()
                .body(Map.class);
        List<byte[]> out = new ArrayList<>();
        if (body == null) {
            return out;
        }
        List<Map<String, Object>> panels = (List<Map<String, Object>>) body.getOrDefault("panels", List.of());
        for (Map<String, Object> p : panels) {
            out.add(Base64.getDecoder().decode((String) p.get("image_b64")));
        }
        return out;
    }

    /** Detect + per-region tag + embed one panel crop. */
    @SuppressWarnings("unchecked")
    public IndexResult indexPanel(byte[] panelBytes) {
        Map<String, Object> body = ml.post()
                .uri("/index-panel")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(imagePart(panelBytes, "panel.png"))
                .retrieve()
                .body(Map.class);
        if (body == null) {
            return new IndexResult(null, Map.of(), Map.of(), List.of());
        }
        float[] embedding = null;
        Object emb = body.get("embedding");
        if (emb instanceof List<?> list) {
            embedding = new float[list.size()];
            for (int i = 0; i < list.size(); i++) {
                embedding[i] = ((Number) list.get(i)).floatValue();
            }
        }
        Map<String, Double> tags = toDoubleMap((Map<String, Object>) body.getOrDefault("tags", Map.of()));
        Map<String, String> sources = new java.util.HashMap<>();
        ((Map<String, Object>) body.getOrDefault("tag_sources", Map.of()))
                .forEach((k, v) -> sources.put(k, String.valueOf(v)));
        List<SubElement> subs = new ArrayList<>();
        for (Map<String, Object> s : (List<Map<String, Object>>) body.getOrDefault("sub_elements", List.of())) {
            subs.add(new SubElement(
                    (String) s.get("label"),
                    (Map<String, Object>) s.get("bbox"),
                    s.get("score") == null ? 0.0 : ((Number) s.get("score")).doubleValue()));
        }
        return new IndexResult(embedding, tags, sources, subs);
    }

    private static Map<String, Double> toDoubleMap(Map<String, Object> in) {
        Map<String, Double> out = new java.util.HashMap<>();
        in.forEach((k, v) -> out.put(k, ((Number) v).doubleValue()));
        return out;
    }

    private static MultiValueMap<String, Object> imagePart(byte[] bytes, String filename) {
        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return filename;
            }
        };
        MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
        parts.add("image", resource);
        return parts;
    }
}

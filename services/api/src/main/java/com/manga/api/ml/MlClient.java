package com.manga.api.ml;

import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Thin client for the Python ml service. Only /embed-text is needed by search. */
@Component
public class MlClient {

    private final RestClient ml;

    public MlClient(RestClient mlRestClient) {
        this.ml = mlRestClient;
    }

    /**
     * CLIP text embedding for the vibes fallback. Returns null on any failure so
     * search degrades to tag/label-only rather than erroring.
     */
    @SuppressWarnings("unchecked")
    public float[] embedText(String text) {
        try {
            Map<String, Object> body = ml.post()
                    .uri("/embed-text")
                    .body(Map.of("text", text))
                    .retrieve()
                    .body(Map.class);
            if (body == null || body.get("embedding") == null) {
                return null;
            }
            List<Number> emb = (List<Number>) body.get("embedding");
            float[] out = new float[emb.size()];
            for (int i = 0; i < emb.size(); i++) {
                out[i] = emb.get(i).floatValue();
            }
            return out;
        } catch (Exception e) {
            return null;
        }
    }
}

package com.manga.api.search;

import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Component;

/**
 * Query -> booru-tag expansion and matching. Direct port of the Python
 * search view's _TAG_SYNONYMS / _LOOSE_TAGS / _query_candidates /
 * _match_stored_tags / _query_labels, so ranking parity is preserved.
 */
@Component
public class QueryExpander {

    /** Ambiguous signals that occur across many emotions -> matched at reduced weight. */
    static final Set<String> LOOSE_TAGS = Set.of(
            "clenched_teeth", "teeth", "open_mouth", "wide_eyed", "sweatdrop", "sweat",
            "light_blush", "spoken_exclamation_mark", "spoken_question_mark", "!", "!?",
            "frown", "pout", "portrait", "close_up");

    /** Query word -> candidate booru tags (only tags that exist in the WD vocabulary). */
    static final Map<String, List<String>> TAG_SYNONYMS = new HashMap<>();
    /** Query token -> sub-element label to boost when that region was detected. */
    static final Map<String, String> LABEL_SYNONYMS = new HashMap<>();

    static {
        // ---- angry ----
        TAG_SYNONYMS.put("angry", List.of("angry", "annoyed", "scowl", "glaring", "v-shaped_eyebrows", "furrowed_brow", "frown", "pout", "clenched_teeth"));
        TAG_SYNONYMS.put("mad", List.of("angry", "annoyed", "scowl", "glaring", "clenched_teeth"));
        TAG_SYNONYMS.put("anger", List.of("angry", "annoyed", "scowl", "glaring"));
        TAG_SYNONYMS.put("furious", List.of("angry", "scowl", "glaring", "clenched_teeth"));
        TAG_SYNONYMS.put("rage", List.of("angry", "scowl", "glaring", "clenched_teeth"));
        TAG_SYNONYMS.put("annoyed", List.of("annoyed", "angry", "pout", "frown"));
        TAG_SYNONYMS.put("irritated", List.of("annoyed", "angry", "frown"));
        // ---- surprised / shocked ----
        TAG_SYNONYMS.put("surprised", List.of("surprised", "wide-eyed", "open_mouth", "spoken_exclamation_mark"));
        TAG_SYNONYMS.put("surprise", List.of("surprised", "wide-eyed", "open_mouth"));
        TAG_SYNONYMS.put("shocked", List.of("surprised", "wide-eyed", "open_mouth", "spoken_exclamation_mark"));
        TAG_SYNONYMS.put("shock", List.of("surprised", "wide-eyed", "open_mouth"));
        TAG_SYNONYMS.put("startled", List.of("surprised", "wide-eyed", "open_mouth"));
        TAG_SYNONYMS.put("astonished", List.of("surprised", "wide-eyed", "open_mouth"));
        TAG_SYNONYMS.put("amazed", List.of("surprised", "wide-eyed"));
        // ---- embarrassed / shy ----
        TAG_SYNONYMS.put("embarrassed", List.of("embarrassed", "flustered", "blush", "full-face_blush", "shy", "light_blush", "nervous_sweating"));
        TAG_SYNONYMS.put("embarrassment", List.of("embarrassed", "flustered", "blush", "full-face_blush"));
        TAG_SYNONYMS.put("flustered", List.of("flustered", "embarrassed", "blush", "full-face_blush"));
        TAG_SYNONYMS.put("shy", List.of("shy", "embarrassed", "blush", "light_blush"));
        TAG_SYNONYMS.put("bashful", List.of("shy", "embarrassed", "blush"));
        TAG_SYNONYMS.put("blush", List.of("blush", "full-face_blush", "light_blush", "embarrassed"));
        TAG_SYNONYMS.put("blushing", List.of("blush", "full-face_blush", "embarrassed"));
        // ---- sad / crying ----
        TAG_SYNONYMS.put("sad", List.of("sad", "crying", "tears", "streaming_tears", "depressed", "frown"));
        TAG_SYNONYMS.put("crying", List.of("crying", "crying_with_eyes_open", "tears", "streaming_tears"));
        TAG_SYNONYMS.put("cry", List.of("crying", "tears", "streaming_tears"));
        TAG_SYNONYMS.put("tears", List.of("tears", "streaming_tears", "crying"));
        TAG_SYNONYMS.put("sobbing", List.of("crying", "streaming_tears", "crying_with_eyes_open"));
        TAG_SYNONYMS.put("upset", List.of("sad", "crying", "frown", "depressed"));
        TAG_SYNONYMS.put("depressed", List.of("depressed", "sad", "expressionless"));
        TAG_SYNONYMS.put("disappointed", List.of("frown", "sad", "depressed"));
        // ---- happy ----
        TAG_SYNONYMS.put("happy", List.of("happy", "smile", "grin", "laughing", "light_smile"));
        TAG_SYNONYMS.put("smile", List.of("smile", "grin", "happy", "light_smile"));
        TAG_SYNONYMS.put("smiling", List.of("smile", "grin", "happy", "light_smile"));
        TAG_SYNONYMS.put("grin", List.of("grin", "smile", "evil_smile"));
        TAG_SYNONYMS.put("joyful", List.of("happy", "smile", "laughing"));
        TAG_SYNONYMS.put("cheerful", List.of("happy", "smile", "grin"));
        TAG_SYNONYMS.put("laughing", List.of("laughing", "grin", "open_mouth"));
        // ---- scared / nervous ----
        TAG_SYNONYMS.put("scared", List.of("scared", "trembling", "panicking", "nervous", "wince", "nervous_sweating"));
        TAG_SYNONYMS.put("afraid", List.of("scared", "trembling", "nervous", "panicking"));
        TAG_SYNONYMS.put("fear", List.of("scared", "trembling", "panicking", "nervous"));
        TAG_SYNONYMS.put("fearful", List.of("scared", "trembling", "nervous"));
        TAG_SYNONYMS.put("terrified", List.of("scared", "trembling", "panicking"));
        TAG_SYNONYMS.put("frightened", List.of("scared", "trembling", "panicking"));
        TAG_SYNONYMS.put("nervous", List.of("nervous", "nervous_sweating", "worried", "sweatdrop", "trembling"));
        TAG_SYNONYMS.put("anxious", List.of("nervous", "worried", "nervous_sweating"));
        TAG_SYNONYMS.put("worried", List.of("worried", "nervous", "frown"));
        TAG_SYNONYMS.put("panic", List.of("panicking", "scared", "nervous_sweating"));
        TAG_SYNONYMS.put("panicking", List.of("panicking", "scared", "nervous_sweating"));
        // ---- other expressions ----
        TAG_SYNONYMS.put("serious", List.of("serious", "expressionless"));
        TAG_SYNONYMS.put("stern", List.of("serious", "frown", "expressionless"));
        TAG_SYNONYMS.put("expressionless", List.of("expressionless", "serious"));
        TAG_SYNONYMS.put("deadpan", List.of("expressionless", "serious", "bored"));
        TAG_SYNONYMS.put("blank", List.of("expressionless"));
        TAG_SYNONYMS.put("smug", List.of("smug", "evil_smile", "grin"));
        TAG_SYNONYMS.put("smirk", List.of("smug", "evil_smile"));
        TAG_SYNONYMS.put("confident", List.of("smug", "grin"));
        TAG_SYNONYMS.put("confused", List.of("confused", "thinking", "spoken_question_mark"));
        TAG_SYNONYMS.put("puzzled", List.of("confused", "thinking"));
        TAG_SYNONYMS.put("disgust", List.of("disgust", "frown"));
        TAG_SYNONYMS.put("disgusted", List.of("disgust", "frown"));
        TAG_SYNONYMS.put("bored", List.of("bored", "expressionless", "sleepy"));
        TAG_SYNONYMS.put("sleepy", List.of("sleepy", "bored"));
        TAG_SYNONYMS.put("tired", List.of("sleepy", "bored"));
        TAG_SYNONYMS.put("evil", List.of("yandere", "crazy_eyes", "evil_smile"));
        TAG_SYNONYMS.put("creepy", List.of("yandere", "crazy_eyes"));
        TAG_SYNONYMS.put("crazy", List.of("crazy_eyes", "yandere"));
        TAG_SYNONYMS.put("yandere", List.of("yandere", "crazy_eyes", "evil_smile"));
        TAG_SYNONYMS.put("screaming", List.of("screaming", "open_mouth"));
        TAG_SYNONYMS.put("yelling", List.of("screaming", "open_mouth"));
        TAG_SYNONYMS.put("shouting", List.of("screaming", "open_mouth"));
        TAG_SYNONYMS.put("pain", List.of("wince", "clenched_teeth"));
        TAG_SYNONYMS.put("hurt", List.of("wince", "clenched_teeth"));
        // ---- non-emotion content ----
        TAG_SYNONYMS.put("chibi", List.of("chibi", "super_deformed"));
        TAG_SYNONYMS.put("eyes", List.of("eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"));
        TAG_SYNONYMS.put("eye", List.of("eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"));
        TAG_SYNONYMS.put("face", List.of("face", "portrait", "close-up"));
        TAG_SYNONYMS.put("faces", List.of("face", "portrait", "close-up"));
        TAG_SYNONYMS.put("hand", List.of("hand", "hands", "clenched_hand", "open_hand", "pointing", "fist", "waving"));
        TAG_SYNONYMS.put("hands", List.of("hand", "hands", "clenched_hand", "open_hand", "pointing", "fist"));
        TAG_SYNONYMS.put("fight", List.of("fighting", "battle", "punching", "kicking", "motion_lines", "speed_lines", "weapon", "sword"));
        TAG_SYNONYMS.put("action", List.of("motion_lines", "speed_lines", "fighting", "battle", "explosion"));

        LABEL_SYNONYMS.put("eye", "eyes");
        LABEL_SYNONYMS.put("eyes", "eyes");
        LABEL_SYNONYMS.put("face", "face");
        LABEL_SYNONYMS.put("faces", "face");
        LABEL_SYNONYMS.put("portrait", "face");
        LABEL_SYNONYMS.put("hand", "hand");
        LABEL_SYNONYMS.put("hands", "hand");
        LABEL_SYNONYMS.put("person", "person");
        LABEL_SYNONYMS.put("people", "person");
        LABEL_SYNONYMS.put("character", "person");
        LABEL_SYNONYMS.put("girl", "person");
        LABEL_SYNONYMS.put("boy", "person");
        LABEL_SYNONYMS.put("man", "person");
        LABEL_SYNONYMS.put("woman", "person");
    }

    static String normalize(String text) {
        return text.strip().toLowerCase().replace(' ', '_').replace('-', '_');
    }

    /** {candidate -> weight}: literal query words 1.0, synonyms 0.8, loose 0.45. */
    Map<String, Double> queryCandidates(String query) {
        String q = normalize(query);
        Map<String, Double> cands = new HashMap<>();
        cands.put(q, 1.0);
        for (String tok : q.split("_")) {
            if (!tok.isEmpty()) {
                cands.put(tok, 1.0);
            }
        }
        java.util.List<String> keys = new java.util.ArrayList<>(Arrays.asList(q.split("_")));
        keys.add(query.strip().toLowerCase());
        for (String tok : keys) {
            for (String syn : TAG_SYNONYMS.getOrDefault(tok, List.of())) {
                String n = normalize(syn);
                double w = LOOSE_TAGS.contains(n) ? 0.45 : 0.8;
                cands.merge(n, w, Math::max);
            }
        }
        cands.keySet().removeIf(String::isEmpty);
        return cands;
    }

    /** {stored_tag -> weight}: candidate must be same-or-more-general than the tag. */
    Map<String, Double> matchStoredTags(Map<String, Double> candidates, List<String> storedTags) {
        Map<String, Double> matched = new HashMap<>();
        for (String st : storedTags) {
            String stNorm = normalize(st);
            Set<String> stTokens = new HashSet<>(Arrays.asList(stNorm.split("_")));
            for (Map.Entry<String, Double> e : candidates.entrySet()) {
                String c = e.getKey();
                double cw = e.getValue();
                if (c.isEmpty()) {
                    continue;
                }
                if (c.equals(stNorm)) {
                    matched.merge(st, 1.0 * cw, Math::max);
                    continue;
                }
                Set<String> cTokens = new HashSet<>(Arrays.asList(c.split("_")));
                if (stTokens.containsAll(cTokens)) {
                    matched.merge(st, 0.7 * cw, Math::max);
                }
            }
        }
        return matched;
    }

    Set<String> queryLabels(String query) {
        Set<String> labels = new HashSet<>();
        for (String tok : normalize(query).split("_")) {
            if (LABEL_SYNONYMS.containsKey(tok)) {
                labels.add(LABEL_SYNONYMS.get(tok));
            }
        }
        return labels;
    }

    boolean isLoose(String tag) {
        return LOOSE_TAGS.contains(normalize(tag));
    }
}

"""
GET /search?q=<text>

Hybrid, tag-first search
------------------------
The old engine ranked purely by CLIP ViT-B-32 cosine distance.  Generic CLIP is
a natural-photo model and scores nearly at random on B&W manga, so queries like
"eyes" returned unrelated panels.  This version leads with booru tags (from the
WD anime tagger) which match the exact vocabulary users search in, and uses CLIP
only as a "vibes" fallback for free-text queries with no tag match.

Ranking for each candidate panel:
    final = tag_score + LABEL_WEIGHT * label_bonus + VECTOR_WEIGHT * vector_sim

  * tag_score   — summed confidence of the panel's tags that match the query
                  (via a synonym map + underscore-token overlap).
  * label_bonus — +1 per matched sub-element type actually detected in the panel
                  (e.g. query "eyes" boosts panels with a detected eye region).
  * vector_sim  — 1 - cosine_distance of the query's CLIP embedding to the panel
                  embedding; dominates only when nothing matches by tag/label.

Panels that match by tag/label always outrank pure-vector matches, so results
"populate correctly" for concept queries while free-text still returns something.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from pgvector.django import CosineDistance

from api.embedding import generate_text_embedding
from api.models import PanelSubElement, PanelTag, StoredPanel

FINAL_K = 30          # results returned to the client
VECTOR_TOP_K = 60     # panels pulled from the vector index for the vibes fallback
LABEL_WEIGHT = 0.4    # bonus per matched sub-element type present in a panel
VECTOR_WEIGHT = 0.25  # weight of CLIP vibes similarity in the blend
TAGS_IN_RESULT = 16   # how many of a panel's own tags to return for display

# Query word -> candidate booru tags. Only tags that actually exist in the WD
# EVA02 vocabulary are listed here (verified against its label set), so a query
# word maps onto real emotion/content signals. Near-synonym query words that are
# NOT themselves tags (e.g. "shocked", "fear", "furious") deliberately map onto
# the tags that *do* exist for that concept. Emotion groups are grouped together
# and kept mutually exclusive enough that one emotion won't pull another's tags
# (e.g. "angry" never maps to "blush").
_TAG_SYNONYMS: dict[str, list[str]] = {
    # ---- angry ---------------------------------------------------------
    "angry": ["angry", "annoyed", "scowl", "glaring", "v-shaped_eyebrows",
              "furrowed_brow", "frown", "pout", "clenched_teeth"],
    "mad": ["angry", "annoyed", "scowl", "glaring", "clenched_teeth"],
    "anger": ["angry", "annoyed", "scowl", "glaring"],
    "furious": ["angry", "scowl", "glaring", "clenched_teeth"],
    "rage": ["angry", "scowl", "glaring", "clenched_teeth"],
    "annoyed": ["annoyed", "angry", "pout", "frown"],
    "irritated": ["annoyed", "angry", "frown"],
    # ---- surprised / shocked ------------------------------------------
    "surprised": ["surprised", "wide-eyed", "open_mouth", "spoken_exclamation_mark"],
    "surprise": ["surprised", "wide-eyed", "open_mouth"],
    "shocked": ["surprised", "wide-eyed", "open_mouth", "spoken_exclamation_mark"],
    "shock": ["surprised", "wide-eyed", "open_mouth"],
    "startled": ["surprised", "wide-eyed", "open_mouth"],
    "astonished": ["surprised", "wide-eyed", "open_mouth"],
    "amazed": ["surprised", "wide-eyed"],
    # ---- embarrassed / shy --------------------------------------------
    "embarrassed": ["embarrassed", "flustered", "blush", "full-face_blush", "shy",
                    "light_blush", "nervous_sweating"],
    "embarrassment": ["embarrassed", "flustered", "blush", "full-face_blush"],
    "flustered": ["flustered", "embarrassed", "blush", "full-face_blush"],
    "shy": ["shy", "embarrassed", "blush", "light_blush"],
    "bashful": ["shy", "embarrassed", "blush"],
    "blush": ["blush", "full-face_blush", "light_blush", "embarrassed"],
    "blushing": ["blush", "full-face_blush", "embarrassed"],
    # ---- sad / crying -------------------------------------------------
    "sad": ["sad", "crying", "tears", "streaming_tears", "depressed", "frown"],
    "crying": ["crying", "crying_with_eyes_open", "tears", "streaming_tears"],
    "cry": ["crying", "tears", "streaming_tears"],
    "tears": ["tears", "streaming_tears", "crying"],
    "sobbing": ["crying", "streaming_tears", "crying_with_eyes_open"],
    "upset": ["sad", "crying", "frown", "depressed"],
    "depressed": ["depressed", "sad", "expressionless"],
    "disappointed": ["frown", "sad", "depressed"],
    # ---- happy --------------------------------------------------------
    "happy": ["happy", "smile", "grin", "laughing", "light_smile"],
    "smile": ["smile", "grin", "happy", "light_smile"],
    "smiling": ["smile", "grin", "happy", "light_smile"],
    "grin": ["grin", "smile", "evil_smile"],
    "joyful": ["happy", "smile", "laughing"],
    "cheerful": ["happy", "smile", "grin"],
    "laughing": ["laughing", "grin", "open_mouth"],
    # ---- scared / nervous ---------------------------------------------
    "scared": ["scared", "trembling", "panicking", "nervous", "wince", "nervous_sweating"],
    "afraid": ["scared", "trembling", "nervous", "panicking"],
    "fear": ["scared", "trembling", "panicking", "nervous"],
    "fearful": ["scared", "trembling", "nervous"],
    "terrified": ["scared", "trembling", "panicking"],
    "frightened": ["scared", "trembling", "panicking"],
    "nervous": ["nervous", "nervous_sweating", "worried", "sweatdrop", "trembling"],
    "anxious": ["nervous", "worried", "nervous_sweating"],
    "worried": ["worried", "nervous", "frown"],
    "panic": ["panicking", "scared", "nervous_sweating"],
    "panicking": ["panicking", "scared", "nervous_sweating"],
    # ---- other expressions --------------------------------------------
    "serious": ["serious", "expressionless"],
    "stern": ["serious", "frown", "expressionless"],
    "expressionless": ["expressionless", "serious"],
    "deadpan": ["expressionless", "serious", "bored"],
    "blank": ["expressionless"],
    "smug": ["smug", "evil_smile", "grin"],
    "smirk": ["smug", "evil_smile"],
    "confident": ["smug", "grin"],
    "confused": ["confused", "thinking", "spoken_question_mark"],
    "puzzled": ["confused", "thinking"],
    "disgust": ["disgust", "frown"],
    "disgusted": ["disgust", "frown"],
    "bored": ["bored", "expressionless", "sleepy"],
    "sleepy": ["sleepy", "bored"],
    "tired": ["sleepy", "bored"],
    "evil": ["yandere", "crazy_eyes", "evil_smile"],
    "creepy": ["yandere", "crazy_eyes"],
    "crazy": ["crazy_eyes", "yandere"],
    "yandere": ["yandere", "crazy_eyes", "evil_smile"],
    "screaming": ["screaming", "open_mouth"],
    "yelling": ["screaming", "open_mouth"],
    "shouting": ["screaming", "open_mouth"],
    "pain": ["wince", "clenched_teeth"],
    "hurt": ["wince", "clenched_teeth"],
    # ---- non-emotion content ------------------------------------------
    "chibi": ["chibi", "super_deformed"],
    "eyes": ["eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"],
    "eye": ["eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"],
    "face": ["face", "portrait", "close-up"],
    "faces": ["face", "portrait", "close-up"],
    "hand": ["hand", "hands", "clenched_hand", "open_hand", "pointing", "fist", "waving"],
    "hands": ["hand", "hands", "clenched_hand", "open_hand", "pointing", "fist"],
    "fight": ["fighting", "battle", "punching", "kicking", "motion_lines",
              "speed_lines", "weapon", "sword"],
    "action": ["motion_lines", "speed_lines", "fighting", "battle", "explosion"],
}

# Query token -> sub-element label to boost when that region was detected.
_LABEL_SYNONYMS: dict[str, str] = {
    "eye": "eyes", "eyes": "eyes",
    "face": "face", "faces": "face", "portrait": "face",
    "hand": "hand", "hands": "hand",
    "person": "person", "people": "person", "character": "person",
    "girl": "person", "boy": "person", "man": "person", "woman": "person",
}


# Ambiguous signals that occur across several emotions/contexts (stored here in
# normalized, underscored form). They match at reduced weight so they only nudge
# ranking rather than define it — e.g. "open_mouth" shouldn't make a talking
# panel read as "surprised", and "clenched_teeth" shouldn't equal "angry".
_LOOSE_TAGS = {
    "clenched_teeth", "teeth", "open_mouth", "wide_eyed", "sweatdrop", "sweat",
    "light_blush", "spoken_exclamation_mark",
    "spoken_question_mark", "!", "!?", "frown", "pout", "portrait", "close_up",
}


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _query_candidates(query: str) -> dict[str, float]:
    """
    Candidate booru tags (normalized) implied by the query, each with a
    confidence weight: the literal query words are trusted (1.0), synonyms less
    so (0.7), and loosely-correlated synonyms least (0.45).  This keeps a fuzzy
    expansion like angry->clenched_teeth from outranking a literal `angry` tag.
    """
    q = _normalize(query)
    cands: dict[str, float] = {q: 1.0}
    for tok in q.split("_"):
        if tok:
            cands[tok] = 1.0
    for tok in list(q.split("_")) + [query.strip().lower()]:
        for syn in _TAG_SYNONYMS.get(tok, []):
            n = _normalize(syn)
            w = 0.45 if n in _LOOSE_TAGS else 0.8
            cands[n] = max(cands.get(n, 0.0), w)
    return {c: w for c, w in cands.items() if c}


def _match_stored_tags(candidates: dict[str, float], stored_tags: list[str]) -> dict[str, float]:
    """
    Map query candidates to actual stored tags, returning ``{stored_tag: weight}``.

    A candidate matches a stored tag only when the candidate is the *same as* or
    *more general than* the stored tag (exact, or the candidate's tokens are a
    subset of the stored tag's — e.g. "eyes" -> "closed_eyes").  It deliberately
    does NOT match when the stored tag is more general than the candidate (e.g.
    the synonym "clenched_teeth" must not match a bare "teeth" tag on a grin).
    """
    matched: dict[str, float] = {}
    for st in stored_tags:
        st_norm = _normalize(st)
        st_tokens = set(st_norm.split("_"))
        for c, cw in candidates.items():
            if not c:
                continue
            if c == st_norm:
                matched[st] = max(matched.get(st, 0.0), 1.0 * cw)
                continue
            c_tokens = set(c.split("_"))
            # candidate is same-or-more-general than the stored tag only
            # (candidate tokens are a subset of the stored tag's tokens)
            if c_tokens <= st_tokens:
                matched[st] = max(matched.get(st, 0.0), 0.7 * cw)
    return matched


def _query_labels(query: str) -> set[str]:
    tokens = {t for t in _normalize(query).split("_") if t}
    return {_LABEL_SYNONYMS[t] for t in tokens if t in _LABEL_SYNONYMS}


@require_GET
def search(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"panels": []})

    # accumulator: panel_id -> scoring parts. "specific_score" counts only
    # non-loose tag matches, so a panel matching just an ambiguous tag like
    # open_mouth doesn't count as a real (strong) hit.
    acc: dict[int, dict] = defaultdict(
        lambda: {"tag_score": 0.0, "specific_score": 0.0, "labels": set(),
                 "matched_tags": set(), "vector_sim": 0.0}
    )
    panels_by_id: dict[int, StoredPanel] = {}

    try:
        # ---- 1. tag matching -------------------------------------------
        candidates = _query_candidates(q)
        distinct_tags = list(
            PanelTag.objects.values_list("tag", flat=True).distinct()
        )
        matched_tag_weights = _match_stored_tags(candidates, distinct_tags)

        if matched_tag_weights:
            tag_rows = (
                PanelTag.objects.filter(tag__in=list(matched_tag_weights.keys()))
                .values("panel_id", "tag", "score")
            )
            for row in tag_rows:
                pid = row["panel_id"]
                tag = row["tag"]
                w = matched_tag_weights.get(tag, 0.0)
                contribution = float(row["score"]) * w
                acc[pid]["tag_score"] += contribution
                acc[pid]["matched_tags"].add(tag)
                if _normalize(tag) not in _LOOSE_TAGS:
                    acc[pid]["specific_score"] += contribution

        # ---- 2. sub-element label matching -----------------------------
        wanted_labels = _query_labels(q)
        if wanted_labels:
            sub_rows = (
                PanelSubElement.objects.filter(label__in=list(wanted_labels))
                .values_list("panel_id", "label")
                .distinct()
            )
            for pid, label in sub_rows:
                acc[pid]["labels"].add(label)

        # ---- 3. vector vibes fallback ----------------------------------
        query_embedding = generate_text_embedding(q)
        if query_embedding:
            vec_hits = (
                StoredPanel.objects.exclude(embedding=None)
                .annotate(distance=CosineDistance("embedding", query_embedding))
                .order_by("distance")[:VECTOR_TOP_K]
            )
            for panel in vec_hits:
                pid = panel.id
                acc[pid]["vector_sim"] = max(0.0, 1.0 - float(panel.distance))
                panels_by_id[pid] = panel

        # ---- fetch any panel objects we scored by tag/label but not vector
        missing = [pid for pid in acc if pid not in panels_by_id]
        if missing:
            for panel in StoredPanel.objects.filter(id__in=missing).select_related("chapter"):
                panels_by_id[panel.id] = panel

    except Exception as e:  # pragma: no cover - surfaces misconfig instead of faking results
        import logging
        logging.getLogger(__name__).exception("Search failed")
        return JsonResponse({"error": f"Search failed: {e}"}, status=500)

    # ---- 4. blend + rank -----------------------------------------------
    # "strong"  = matched a specific (non-loose) tag or a detected sub-element.
    # "weak"    = matched only ambiguous loose tags (e.g. open_mouth alone).
    # "vibes"   = CLIP similarity only.
    # Strong results are returned alone when present; weak/vibes are the honest
    # fallback only when nothing specific matched — this stops loose tags from
    # padding an emotion query with unrelated face panels.
    strong: list = []
    weak: list = []
    for pid, parts in acc.items():
        panel = panels_by_id.get(pid)
        if panel is None:
            continue
        final = (
            parts["tag_score"]
            + LABEL_WEIGHT * len(parts["labels"])
            + VECTOR_WEIGHT * parts["vector_sim"]
        )
        if final <= 0:
            continue
        is_strong = parts["specific_score"] > 0 or bool(parts["labels"])
        (strong if is_strong else weak).append((final, pid, panel, parts))

    strong.sort(key=lambda t: -t[0])
    weak.sort(key=lambda t: -t[0])

    scored = strong[:FINAL_K] if strong else weak[:FINAL_K]

    results = []
    for final, pid, panel, parts in scored:
        if parts["specific_score"] > 0:
            matched_via = "tag"
        elif parts["labels"]:
            matched_via = "sub_element"
        elif parts["tag_score"] > 0:
            matched_via = "related"  # only loose/ambiguous tags matched
        else:
            matched_via = "vibes"
        # Show the matched tags most relevant to the query first (by match weight,
        # then score), not alphabetically — so the real emotion tag leads.
        matched_sorted = sorted(
            parts["matched_tags"],
            key=lambda t: (-matched_tag_weights.get(t, 0.0), -(panel.tags or {}).get(t, 0.0), t),
        )
        top_tags = [
            t for t, _s in sorted((panel.tags or {}).items(), key=lambda kv: -kv[1])
        ][:TAGS_IN_RESULT]
        results.append(
            {
                "id": panel.id,
                "chapter_id": panel.chapter.chapter_id,
                "page_index": panel.page_index,
                "panel_index": panel.panel_index,
                "url": panel.public_url,
                "matched_via": matched_via,
                "score": round(final, 4),
                "similarity": round(parts["vector_sim"], 4),
                "matched_tags": matched_sorted,
                "matched_labels": sorted(parts["labels"]),
                "tags": top_tags,
            }
        )

    return JsonResponse({"panels": results})

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
MAX_VIBES_FILLER = 6  # vibes-only panels to append when strong matches exist

# Query token -> extra candidate booru tags that aren't obvious by string overlap.
_TAG_SYNONYMS: dict[str, list[str]] = {
    "angry": ["angry", "anger", "annoyed", "clenched_teeth", "v-shaped_eyebrows",
              "scowl", "glaring", "frown", "furrowed_brow", "pout", "rage"],
    "mad": ["angry", "annoyed", "clenched_teeth", "scowl", "glaring"],
    "chibi": ["chibi", "super_deformed"],
    "eyes": ["eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"],
    "eye": ["eye", "eyes", "closed_eyes", "one_eye_closed", "glowing_eyes"],
    "face": ["face", "portrait", "close-up", "expressionless"],
    "faces": ["face", "portrait", "close-up"],
    "hand": ["hand", "hands", "clenched_hand", "open_hand", "pointing", "fist", "waving"],
    "hands": ["hand", "hands", "clenched_hand", "open_hand", "pointing", "fist"],
    "smile": ["smile", "grin", "happy", "smiling"],
    "smiling": ["smile", "grin", "happy"],
    "happy": ["smile", "grin", "happy", "laughing"],
    "sad": ["tears", "crying", "sad", "depressed", "streaming_tears"],
    "crying": ["tears", "crying", "streaming_tears", "tearing_up"],
    "surprised": ["surprised", "shocked", "open_mouth", "wide-eyed"],
    "shocked": ["surprised", "shocked", "open_mouth", "wide-eyed"],
    "blush": ["blush", "embarrassed", "blushing"],
    "fight": ["fighting", "battle", "punching", "kicking", "motion_lines",
              "speed_lines", "weapon", "sword", "action"],
    "action": ["motion_lines", "speed_lines", "fighting", "battle", "explosion"],
    "scared": ["scared", "fear", "sweatdrop", "trembling", "nervous"],
}

# Query token -> sub-element label to boost when that region was detected.
_LABEL_SYNONYMS: dict[str, str] = {
    "eye": "eyes", "eyes": "eyes",
    "face": "face", "faces": "face", "portrait": "face",
    "hand": "hand", "hands": "hand",
    "person": "person", "people": "person", "character": "person",
    "girl": "person", "boy": "person", "man": "person", "woman": "person",
}


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _query_candidates(query: str) -> set[str]:
    """Candidate booru tags (normalized) implied by the query text."""
    q = _normalize(query)
    tokens = {t for t in q.split("_") if t}
    candidates: set[str] = {q} | tokens
    for tok in list(tokens) + [query.strip().lower()]:
        candidates.update(_normalize(c) for c in _TAG_SYNONYMS.get(tok, []))
    return {c for c in candidates if c}


def _match_stored_tags(candidates: set[str], stored_tags: list[str]) -> dict[str, float]:
    """Map query candidates to actual stored tags, with a match weight (0-1)."""
    matched: dict[str, float] = {}
    for st in stored_tags:
        st_norm = _normalize(st)
        st_tokens = set(st_norm.split("_"))
        for c in candidates:
            if not c:
                continue
            if c == st_norm:
                matched[st] = max(matched.get(st, 0.0), 1.0)
                break
            c_tokens = set(c.split("_"))
            overlap = c_tokens & st_tokens
            if overlap and (c in st_norm or c_tokens <= st_tokens or st_tokens <= c_tokens):
                matched[st] = max(matched.get(st, 0.0), 0.7)
    return matched


def _query_labels(query: str) -> set[str]:
    tokens = {t for t in _normalize(query).split("_") if t}
    return {_LABEL_SYNONYMS[t] for t in tokens if t in _LABEL_SYNONYMS}


@require_GET
def search(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"panels": []})

    # accumulator: panel_id -> scoring parts
    acc: dict[int, dict] = defaultdict(
        lambda: {"tag_score": 0.0, "labels": set(), "matched_tags": set(), "vector_sim": 0.0}
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
                w = matched_tag_weights.get(row["tag"], 0.0)
                acc[pid]["tag_score"] += float(row["score"]) * w
                acc[pid]["matched_tags"].add(row["tag"])

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
    # "strong" = matched by tag or sub-element; "vibes" = CLIP similarity only.
    # Strong matches always rank first; weak vibes only fill in behind them (and
    # are the sole results when nothing matched by tag/label — the honest fallback).
    strong: list = []
    vibes: list = []
    for pid, parts in acc.items():
        panel = panels_by_id.get(pid)
        if panel is None:
            continue
        is_strong = parts["tag_score"] > 0 or parts["labels"]
        final = (
            parts["tag_score"]
            + LABEL_WEIGHT * len(parts["labels"])
            + VECTOR_WEIGHT * parts["vector_sim"]
        )
        if final <= 0:
            continue
        (strong if is_strong else vibes).append((final, pid, panel, parts))

    strong.sort(key=lambda t: -t[0])
    vibes.sort(key=lambda t: -t[0])

    if strong:
        scored = strong[:FINAL_K] + vibes[:MAX_VIBES_FILLER]
        scored = scored[:FINAL_K]
    else:
        scored = vibes[:FINAL_K]

    results = []
    for final, pid, panel, parts in scored:
        if parts["tag_score"] > 0:
            matched_via = "tag"
        elif parts["labels"]:
            matched_via = "sub_element"
        else:
            matched_via = "vibes"
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
                "matched_tags": sorted(parts["matched_tags"]),
                "matched_labels": sorted(parts["labels"]),
            }
        )

    return JsonResponse({"panels": results})

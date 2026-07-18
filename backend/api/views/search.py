"""
GET /search

Query params:
  q (str): Text search string for vector similarity search.

Search strategy
---------------
1. Embed the query text with OpenCLIP (same model used during ingest).
2. Run two cosine-distance queries in parallel:
   a. StoredPanel.embedding       — whole-panel CLIP embedding
   b. PanelSubElement.embedding   — sub-element crop embeddings (face, hair, hand, clothing)
3. Merge + deduplicate by panel id, keeping the closest (lowest) cosine distance.
4. Return the top 20 panels sorted by best distance.

The response always contains the *panel* image URL — crops are never exposed.
A `matched_via` field indicates whether the hit came from the panel level or a
specific sub-element (useful for debugging / future UI).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from pgvector.django import CosineDistance
from api.models import PanelSubElement, StoredPanel
from api.embedding import generate_text_embedding

TOP_K = 40   # candidates per source before merging
FINAL_K = 20  # results returned to the client


@require_GET
def search(request):
    """
    Vector similarity search across panel-level and sub-element-level embeddings.
    Returns deduplicated panel results sorted by best cosine distance.
    """
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"panels": []})

    query_embedding = generate_text_embedding(q)
    if not query_embedding:
        return JsonResponse({"error": "Failed to generate embedding"}, status=500)

    # Accumulate (panel_id → {distance, panel_obj, matched_via})
    best: dict[int, dict] = {}

    try:
        # --- panel-level search ---
        panel_hits = (
            StoredPanel.objects.exclude(embedding=None)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:TOP_K]
        )
        for panel in panel_hits:
            pid = panel.id
            dist = float(panel.distance)
            if pid not in best or dist < best[pid]["distance"]:
                best[pid] = {
                    "distance": dist,
                    "panel": panel,
                    "matched_via": "panel",
                }

        # --- sub-element search ---
        sub_hits = (
            PanelSubElement.objects.exclude(embedding=None)
            .select_related("panel")
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:TOP_K]
        )
        for sub in sub_hits:
            panel = sub.panel
            pid = panel.id
            dist = float(sub.distance)
            if pid not in best or dist < best[pid]["distance"]:
                best[pid] = {
                    "distance": dist,
                    "panel": panel,
                    "matched_via": f"sub_element:{sub.label}",
                }

    except Exception as e:
        print(f"Vector search failed (likely SQLite or pgvector missing): {e}")
        # Fallback: return arbitrary panels without ranking
        panels = StoredPanel.objects.all()[:FINAL_K]
        results = [
            {
                "id": p.id,
                "chapter_id": p.chapter.chapter_id,
                "page_index": p.page_index,
                "panel_index": p.panel_index,
                "url": p.public_url,
                "matched_via": "fallback",
            }
            for p in panels
        ]
        return JsonResponse({"panels": results})

    # Sort merged results by distance and return top FINAL_K
    sorted_hits = sorted(best.values(), key=lambda h: h["distance"])[:FINAL_K]

    results = [
        {
            "id": h["panel"].id,
            "chapter_id": h["panel"].chapter.chapter_id,
            "page_index": h["panel"].page_index,
            "panel_index": h["panel"].panel_index,
            "url": h["panel"].public_url,
            "matched_via": h["matched_via"],
        }
        for h in sorted_hits
    ]

    return JsonResponse({"panels": results})

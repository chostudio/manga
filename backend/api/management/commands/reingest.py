"""
Re-index existing panels with the reworked pipeline (YOLO panels + anime
detectors + WD booru tags + fixed CLIP embedding).

Two modes per chapter, chosen automatically:

* MangaDex chapters (``quality`` in ``data`` / ``data-saver``) — re-download the
  original pages from MangaDex and re-run the full page pipeline, so panels are
  re-cropped with the YOLO frame detector and fully re-indexed.  Overwrites via
  ``StoredPanel.update_or_create``.

* Direct uploads (``quality == "upload"``) — the original page is gone, so the
  stored panel crops are re-tagged / re-embedded *in place* (no re-crop).

Usage:
    python manage.py reingest              # every chapter
    python manage.py reingest --only <id>  # one chapter_id
    python manage.py reingest --dry-run    # report what would happen, change nothing
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from api.ingest import index_panel
from api.mangadex import (
    MangadexResolveError,
    download_mangadex_at_home_pages,
    resolve_mangadex_chapter_pages,
)
from api.models import ChapterIngestion, StoredPanel
from api.storage import get_object
from api.views.upload_webscrape import _run_page_pipeline

_MANGADEX_QUALITIES = {"data", "data-saver"}


class Command(BaseCommand):
    help = "Re-index existing panels with the reworked detection/tagging pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--only", dest="only", default=None,
                            help="Re-ingest just this chapter_id.")
        parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="Report actions without changing anything.")

    def handle(self, *args, **opts):
        only = opts.get("only")
        dry = opts.get("dry_run")

        chapters = ChapterIngestion.objects.all()
        if only:
            chapters = chapters.filter(chapter_id=only)
        chapters = list(chapters)

        if not chapters:
            self.stdout.write(self.style.WARNING("No matching chapters."))
            return

        for ch in chapters:
            if ch.quality in _MANGADEX_QUALITIES:
                self._reingest_mangadex(ch, dry)
            else:
                self._reindex_uploads(ch, dry)

        self.stdout.write(self.style.SUCCESS("reingest complete."))

    # ------------------------------------------------------------------
    def _reingest_mangadex(self, ch: ChapterIngestion, dry: bool) -> None:
        self.stdout.write(f"[mangadex] {ch.chapter_id} ({ch.quality}) — re-downloading pages")
        if dry:
            self.stdout.write("  dry-run: would re-download and re-run the full page pipeline")
            return

        resolved = resolve_mangadex_chapter_pages(ch.chapter_id, ch.quality)
        if isinstance(resolved, MangadexResolveError):
            self.stdout.write(self.style.ERROR(f"  resolve failed: {resolved.body}"))
            return

        results = download_mangadex_at_home_pages(resolved.page_urls)
        ok = 0
        touched: set[tuple[int, int]] = set()  # (page_index, panel_index) kept this run
        for i in range(len(resolved.page_urls)):
            _url, code, data, err = results[i]
            if err or data is None:
                self.stdout.write(self.style.WARNING(f"  page {i}: {err or 'empty'}"))
                continue
            try:
                out = _run_page_pipeline(data, chapter_ingestion=ch, page_index=i)
                ok += 1
                for sp in out["stored_panels"]:
                    touched.add((i, sp["panel_index"]))
                self.stdout.write(f"  page {i}: {out['panel_count']} panels")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  page {i} failed: {e}"))

        # Prune stale panels from pages that now yield fewer panels than before.
        # (Only prune pages we actually re-processed, so a failed download can't wipe data.)
        reprocessed_pages = {p for (p, _n) in touched}
        stale = [
            sp for sp in StoredPanel.objects.filter(chapter=ch)
            if sp.page_index in reprocessed_pages and (sp.page_index, sp.panel_index) not in touched
        ]
        if stale:
            StoredPanel.objects.filter(id__in=[sp.id for sp in stale]).delete()
            self.stdout.write(self.style.WARNING(f"  pruned {len(stale)} stale panels"))

        self.stdout.write(self.style.SUCCESS(f"  re-ingested {ok}/{len(resolved.page_urls)} pages"))

    # ------------------------------------------------------------------
    def _reindex_uploads(self, ch: ChapterIngestion, dry: bool) -> None:
        panels = list(StoredPanel.objects.filter(chapter=ch))
        self.stdout.write(
            f"[upload]   {ch.chapter_id} — re-indexing {len(panels)} stored crops in place "
            "(cannot re-crop; original page unavailable)"
        )
        if dry:
            return
        for p in panels:
            data = get_object(p.storage_key)
            if data is None:
                self.stdout.write(self.style.WARNING(f"  panel {p.pk}: crop bytes missing ({p.storage_key})"))
                continue
            index_panel(p, data)
            tags = sorted((p.tags or {}).keys())
            self.stdout.write(f"  panel {p.pk}: {len(tags)} tags")

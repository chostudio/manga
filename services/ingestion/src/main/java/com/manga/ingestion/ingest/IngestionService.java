package com.manga.ingestion.ingest;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.manga.ingestion.mangadex.MangadexClient;
import com.manga.ingestion.ml.MlClient;
import com.manga.ingestion.persist.PanelWriter;
import com.manga.ingestion.storage.StorageService;

/**
 * Orchestrates ingesting one MangaDex chapter:
 *   resolve pages -> per page: download -> ml.split-panels -> per panel:
 *   store image + ml.index-panel + upsert panel + write tags/sub-elements.
 * Idempotent (upserts + prune), so re-ingesting a chapter overwrites cleanly.
 */
@Service
public class IngestionService {

    private static final Logger log = LoggerFactory.getLogger(IngestionService.class);

    private final MangadexClient mangadex;
    private final MlClient ml;
    private final StorageService storage;
    private final PanelWriter writer;

    public IngestionService(MangadexClient mangadex, MlClient ml, StorageService storage, PanelWriter writer) {
        this.mangadex = mangadex;
        this.ml = ml;
        this.storage = storage;
        this.writer = writer;
    }

    public record Summary(String chapterId, String quality, int pages, int panels) {}

    public Summary ingestChapter(String chapterId, String quality, Consumer<String> progress) {
        MangadexClient.ChapterPages pages = mangadex.resolveChapterPages(chapterId, quality);
        long chapterPk = writer.upsertChapter(chapterId, quality, pages.filenames().size());
        progress.accept("resolved " + pages.pageUrls().size() + " pages");

        List<int[]> keep = new ArrayList<>();
        int totalPanels = 0;
        int pageIndex = 0;
        for (String pageUrl : pages.pageUrls()) {
            try {
                byte[] pageBytes = mangadex.downloadPage(pageUrl);
                List<byte[]> panels = ml.splitPanels(pageBytes);
                for (int panelIndex = 0; panelIndex < panels.size(); panelIndex++) {
                    byte[] panelBytes = panels.get(panelIndex);
                    String key = storage.buildKey(chapterId, quality, pageIndex, panelIndex, "png");
                    StorageService.Stored stored = storage.put(key, panelBytes, "image/png");
                    MlClient.IndexResult idx = ml.indexPanel(panelBytes);
                    long panelId = writer.upsertPanel(
                            chapterPk, pageIndex, panelIndex, stored.key(), stored.byteSize(),
                            stored.contentType(), stored.publicUrl(), idx.embedding(), idx.tags());
                    writer.writeDerived(panelId, idx.tags(), idx.tagSources(), idx.subElements());
                    keep.add(new int[]{pageIndex, panelIndex});
                    totalPanels++;
                }
                progress.accept("page " + pageIndex + ": " + panels.size() + " panels");
            } catch (Exception e) {
                log.warn("page {} failed: {}", pageIndex, e.getMessage());
                progress.accept("page " + pageIndex + " failed: " + e.getMessage());
            }
            pageIndex++;
        }
        writer.pruneStale(chapterPk, keep);
        return new Summary(chapterId, quality, pages.pageUrls().size(), totalPanels);
    }
}

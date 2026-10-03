package com.manga.ingestion.ingest;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import com.manga.ingestion.mangadex.MangadexClient;

/**
 * POST /ingest {url, quality}  -> starts an async ingest job, returns {job_id}.
 * GET  /ingest/{jobId}         -> job status + progress log.
 */
@RestController
public class IngestionController {

    private final JobService jobs;

    public IngestionController(JobService jobs) {
        this.jobs = jobs;
    }

    public record IngestRequest(String url, String quality) {}

    @PostMapping("/ingest")
    public ResponseEntity<?> ingest(@RequestBody IngestRequest req) {
        if (req.url() == null || req.url().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("detail", "url is required"));
        }
        String chapterId = MangadexClient.extractChapterId(req.url());
        if (chapterId == null) {
            return ResponseEntity.status(501).body(Map.of(
                    "detail", "Only MangaDex chapter URLs are supported",
                    "url", req.url()));
        }
        String quality = (req.quality() == null || req.quality().isBlank()) ? "data" : req.quality();
        if (!quality.equals("data") && !quality.equals("data-saver")) {
            return ResponseEntity.badRequest().body(Map.of("detail", "quality must be data or data-saver"));
        }
        JobService.Job job = jobs.start(chapterId, quality);
        return ResponseEntity.accepted().body(job.toView());
    }

    @GetMapping("/ingest/{jobId}")
    public ResponseEntity<?> status(@PathVariable String jobId) {
        JobService.Job job = jobs.get(jobId);
        if (job == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(job.toView());
    }
}

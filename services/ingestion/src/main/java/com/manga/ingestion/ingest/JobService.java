package com.manga.ingestion.ingest;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

/**
 * In-memory async job runner for chapter ingests. This is the seam where a
 * RabbitMQ queue + worker would slot in for horizontal scaling; the API and
 * orchestration stay identical.
 */
@Service
public class JobService {

    public static final class Job {
        public final String id;
        public volatile String state = "RUNNING"; // RUNNING | DONE | ERROR
        public final List<String> log = new CopyOnWriteArrayList<>();
        public volatile IngestionService.Summary summary;

        Job(String id) {
            this.id = id;
        }

        public Map<String, Object> toView() {
            return Map.of(
                    "job_id", id,
                    "state", state,
                    "log", log,
                    "summary", summary == null ? Map.of() : Map.of(
                            "chapter_id", summary.chapterId(),
                            "quality", summary.quality(),
                            "pages", summary.pages(),
                            "panels", summary.panels()));
        }
    }

    private final IngestionService ingestion;
    private final Map<String, Job> jobs = new ConcurrentHashMap<>();

    public JobService(IngestionService ingestion) {
        this.ingestion = ingestion;
    }

    public Job start(String chapterId, String quality) {
        Job job = new Job(UUID.randomUUID().toString());
        jobs.put(job.id, job);
        run(job, chapterId, quality);
        return job;
    }

    public Job get(String id) {
        return jobs.get(id);
    }

    @Async
    void run(Job job, String chapterId, String quality) {
        try {
            job.summary = ingestion.ingestChapter(chapterId, quality, job.log::add);
            job.state = "DONE";
        } catch (Exception e) {
            job.log.add("ERROR: " + e.getMessage());
            job.state = "ERROR";
        }
    }
}

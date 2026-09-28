package com.manga.ingestion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

/**
 * Ingestion service: MangaDex download + orchestration. Calls the Python ml
 * service for panels/tags/embeddings and writes to the shared Postgres + storage.
 */
@EnableAsync
@SpringBootApplication
public class IngestionApplication {
    public static void main(String[] args) {
        SpringApplication.run(IngestionApplication.class, args);
    }
}

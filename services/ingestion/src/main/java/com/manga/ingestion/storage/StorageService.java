package com.manga.ingestion.storage;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * Object storage for panel images. Local filesystem for dev (mirrors the Django
 * storage.py key layout and /media URL so existing served paths keep working);
 * S3 can be added behind the same put() method.
 */
@Service
public class StorageService {

    @Value("${manga.storage.local-dir:../../backend/media/storage}")
    private String localDir;

    @Value("${manga.storage.media-url:/media}")
    private String mediaUrl;

    /** mangadex/{chapter}/{quality}/page_{p:04d}/panel_{n:04d}.{ext} */
    public String buildKey(String chapterId, String quality, int page, int panel, String ext) {
        return String.format("mangadex/%s/%s/page_%04d/panel_%04d.%s",
                chapterId, quality, page, panel, ext.replaceFirst("^\\.", ""));
    }

    public record Stored(String key, long byteSize, String contentType, String publicUrl) {}

    public Stored put(String key, byte[] data, String contentType) {
        try {
            Path dest = Paths.get(localDir).resolve(key);
            Files.createDirectories(dest.getParent());
            Files.write(dest, data);
        } catch (IOException e) {
            throw new IllegalStateException("storage write failed for " + key + ": " + e.getMessage(), e);
        }
        String url = mediaUrl.replaceAll("/+$", "") + "/" + key;
        return new Stored(key, data.length, contentType, url);
    }
}

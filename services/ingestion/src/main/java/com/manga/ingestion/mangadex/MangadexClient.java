package com.manga.ingestion.mangadex;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * MangaDex at-home client (port of the Django mangadex.py): resolve a chapter's
 * page URLs and download page images. Image requests carry no Authorization
 * header (MangaDex requirement) and use a descriptive User-Agent.
 */
@Component
public class MangadexClient {

    private static final String API = "https://api.mangadex.org";
    private static final String USER_AGENT = "MangaIndexer/0.1 (+https://example.com/contact)";
    private static final Pattern CHAPTER_ID = Pattern.compile(
            "/chapter/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            Pattern.CASE_INSENSITIVE);

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30)).build();
    private final ObjectMapper mapper = new ObjectMapper();

    public record ChapterPages(List<String> pageUrls, List<String> filenames) {}

    public static String extractChapterId(String url) {
        if (url == null) {
            return null;
        }
        Matcher m = CHAPTER_ID.matcher(url);
        return m.find() ? m.group(1).toLowerCase() : null;
    }

    /** GET /at-home/server/{id}, build ordered page URLs for the requested quality. */
    public ChapterPages resolveChapterPages(String chapterId, String quality) {
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(API + "/at-home/server/" + chapterId))
                    .header("Accept", "application/json")
                    .header("User-Agent", USER_AGENT)
                    .timeout(Duration.ofSeconds(30))
                    .GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                throw new IllegalStateException("at-home metadata HTTP " + resp.statusCode());
            }
            JsonNode root = mapper.readTree(resp.body());
            if (!"ok".equals(root.path("result").asText())) {
                throw new IllegalStateException("at-home result != ok");
            }
            String baseUrl = root.path("baseUrl").asText();
            JsonNode chapter = root.path("chapter");
            String hash = chapter.path("hash").asText();
            boolean saver = "data-saver".equals(quality);
            JsonNode names = chapter.path(saver ? "dataSaver" : "data");
            if (baseUrl.isEmpty() || hash.isEmpty() || !names.isArray()) {
                throw new IllegalStateException("unexpected at-home response shape");
            }
            String q = saver ? "data-saver" : "data";
            List<String> filenames = new ArrayList<>();
            List<String> urls = new ArrayList<>();
            for (JsonNode n : names) {
                String fn = n.asText();
                filenames.add(fn);
                urls.add(baseUrl.replaceAll("/+$", "") + "/" + q + "/" + hash + "/" + fn);
            }
            return new ChapterPages(urls, filenames);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("MangaDex resolve failed: " + e.getMessage(), e);
        }
    }

    /** Download one page image (no Authorization header). Returns bytes or throws. */
    public byte[] downloadPage(String url) {
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(url))
                    .header("User-Agent", USER_AGENT)
                    .timeout(Duration.ofSeconds(60))
                    .GET().build();
            HttpResponse<byte[]> resp = http.send(req, HttpResponse.BodyHandlers.ofByteArray());
            if (resp.statusCode() != 200 || resp.body().length == 0) {
                throw new IllegalStateException("page HTTP " + resp.statusCode());
            }
            return resp.body();
        } catch (Exception e) {
            throw new IllegalStateException("page download failed: " + e.getMessage(), e);
        }
    }
}

package com.manga.api.search;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** GET /search?q=... — tag-first hybrid panel search (matches the old Django API shape). */
@RestController
public class SearchController {

    private final SearchService searchService;

    public SearchController(SearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping("/search")
    public Map<String, List<SearchResult>> search(@RequestParam(name = "q", defaultValue = "") String q) {
        return Map.of("panels", searchService.search(q));
    }
}

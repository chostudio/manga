package com.manga.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * BFF + search service. Owns the Angular-facing query API and the tag/vector
 * ranking; delegates CLIP text embedding to the Python ml service.
 */
@SpringBootApplication
public class ApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }
}

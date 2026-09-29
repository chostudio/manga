package com.manga.api.config;

import java.nio.file.Paths;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * CORS for the Angular dev server, the RestClient for the ml service, and static
 * serving of panel images from the shared storage dir (the files the ingestion
 * service writes) so the frontend can load /media/... without the old Django.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Value("${manga.cors-origins:http://localhost:4200,http://127.0.0.1:4200}")
    private String[] corsOrigins;

    @Value("${manga.storage.local-dir:../../backend/media/storage}")
    private String storageDir;

    @Value("${manga.storage.media-url:/media}")
    private String mediaUrl;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOrigins(corsOrigins)
                .allowedMethods("GET", "POST", "OPTIONS");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String base = mediaUrl.replaceAll("/+$", "");
        String absolute = Paths.get(storageDir).toAbsolutePath().normalize().toString();
        registry.addResourceHandler(base + "/**")
                .addResourceLocations("file:" + absolute + "/");
    }

    @Bean
    RestClient mlRestClient(@Value("${manga.ml-base-url:http://localhost:8001}") String mlBaseUrl) {
        return RestClient.builder().baseUrl(mlBaseUrl).build();
    }
}

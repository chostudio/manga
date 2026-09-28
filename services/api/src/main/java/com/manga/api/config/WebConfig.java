package com.manga.api.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** CORS for the Angular dev server, and the RestClient used to call the ml service. */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Value("${manga.cors-origins:http://localhost:4200,http://127.0.0.1:4200}")
    private String[] corsOrigins;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOrigins(corsOrigins)
                .allowedMethods("GET", "POST", "OPTIONS");
    }

    @Bean
    RestClient mlRestClient(@Value("${manga.ml-base-url:http://localhost:8001}") String mlBaseUrl) {
        return RestClient.builder().baseUrl(mlBaseUrl).build();
    }
}

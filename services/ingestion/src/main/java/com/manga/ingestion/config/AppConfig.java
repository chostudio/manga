package com.manga.ingestion.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** RestClient for the ml service, with timeouts sized for CPU inference. */
@Configuration
public class AppConfig {

    @Bean
    RestClient mlRestClient(@Value("${manga.ml-base-url:http://localhost:8001}") String mlBaseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(300_000); // EVA02 tagging can take seconds/panel on CPU
        return RestClient.builder().baseUrl(mlBaseUrl).requestFactory(factory).build();
    }
}

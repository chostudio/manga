# Build the Spring Boot ingestion service (multi-stage; small runtime image).
FROM eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN ./gradlew --no-daemon dependencies || true
COPY src ./src
RUN ./gradlew --no-daemon bootJar

FROM eclipse-temurin:21-jre
WORKDIR /srv
COPY --from=build /build/build/libs/*.jar app.jar
EXPOSE 8090
ENTRYPOINT ["java", "-jar", "app.jar"]

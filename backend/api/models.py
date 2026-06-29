from django.db import models
from pgvector.django import VectorField


class ChapterIngestion(models.Model):
    """One MangaDex chapter ingest run (metadata for stored pages/panels)."""

    chapter_id = models.CharField(max_length=36, db_index=True)
    quality = models.CharField(max_length=16)
    page_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chapter_id", "quality"],
                name="uniq_chapter_ingestion_chapter_quality",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.chapter_id} ({self.quality})"


class StoredPanel(models.Model):
    """One stored panel image and its object storage key."""

    chapter = models.ForeignKey(
        ChapterIngestion,
        on_delete=models.CASCADE,
        related_name="panels",
    )
    page_index = models.PositiveIntegerField()
    panel_index = models.PositiveIntegerField()
    storage_key = models.CharField(max_length=512)
    byte_size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=64, default="image/avif")
    public_url = models.URLField(max_length=1024, blank=True)
    embedding = VectorField(dimensions=512, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chapter", "page_index", "panel_index"],
                name="uniq_stored_panel_chapter_page_panel",
            ),
        ]
        ordering = ["page_index", "panel_index"]

    def __str__(self) -> str:
        return f"{self.chapter.chapter_id} p{self.page_index} n{self.panel_index}"

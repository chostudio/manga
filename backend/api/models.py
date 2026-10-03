from django.db import models
from pgvector.django import VectorField

SUB_ELEMENT_LABELS = ("face", "eyes", "hand", "person")


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
    # Raw booru tags for this panel: {tag: score}. Denormalized copy of the
    # PanelTag rows, kept for quick display / debugging.
    tags = models.JSONField(null=True, blank=True)
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


class PanelSubElement(models.Model):
    """
    A semantically meaningful sub-region within a StoredPanel.

    Each row stores the CLIP embedding of a cropped area (face, hair, hand,
    clothing) so those regions can be independently searched.  The search
    result always returns the *parent panel* URL — the crop is never shown.
    """

    LABEL_CHOICES = [(lbl, lbl) for lbl in SUB_ELEMENT_LABELS]

    panel = models.ForeignKey(
        StoredPanel,
        on_delete=models.CASCADE,
        related_name="sub_elements",
    )
    label = models.CharField(max_length=64, choices=LABEL_CHOICES, db_index=True)
    # Bounding box in pixels relative to the panel image (stored for future use)
    bbox = models.JSONField(null=True, blank=True)
    # 512-dim CLIP embedding of the cropped region
    embedding = VectorField(dimensions=512, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["panel", "label"]

    def __str__(self) -> str:
        return f"{self.panel} [{self.label}]"


class PanelTag(models.Model):
    """
    One booru-style tag attached to a StoredPanel, with the tagger's confidence.

    These rows power concept search: a query is mapped to candidate tags and
    panels are ranked by the summed confidence of their matching tags.  ``source``
    records where the tag came from ("panel" = whole panel, "face" = a face crop),
    so face-derived emotion tags can be weighted differently if desired.
    """

    panel = models.ForeignKey(
        StoredPanel,
        on_delete=models.CASCADE,
        related_name="tag_rows",
    )
    tag = models.CharField(max_length=128, db_index=True)
    score = models.FloatField(default=0.0)
    source = models.CharField(max_length=16, default="panel")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["panel", "tag"],
                name="uniq_panel_tag",
            ),
        ]
        indexes = [
            models.Index(fields=["tag", "score"]),
        ]

    def __str__(self) -> str:
        return f"{self.panel} #{self.tag} ({self.score:.2f})"

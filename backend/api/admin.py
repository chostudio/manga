from django.contrib import admin

from api.models import ChapterIngestion, PanelSubElement, StoredPanel


class StoredPanelInline(admin.TabularInline):
    model = StoredPanel
    extra = 0
    readonly_fields = ("storage_key", "byte_size", "content_type", "public_url", "created_at")


class PanelSubElementInline(admin.TabularInline):
    model = PanelSubElement
    extra = 0
    readonly_fields = ("label", "bbox", "created_at")
    fields = ("label", "bbox", "created_at")


@admin.register(ChapterIngestion)
class ChapterIngestionAdmin(admin.ModelAdmin):
    list_display = ("chapter_id", "quality", "page_count", "created_at")
    search_fields = ("chapter_id",)
    inlines = [StoredPanelInline]


@admin.register(StoredPanel)
class StoredPanelAdmin(admin.ModelAdmin):
    list_display = ("chapter", "page_index", "panel_index", "byte_size", "storage_key")
    list_filter = ("content_type",)
    search_fields = ("chapter__chapter_id", "storage_key")
    inlines = [PanelSubElementInline]


@admin.register(PanelSubElement)
class PanelSubElementAdmin(admin.ModelAdmin):
    list_display = ("panel", "label", "created_at")
    list_filter = ("label",)
    search_fields = ("panel__chapter__chapter_id",)

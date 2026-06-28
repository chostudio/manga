from django.contrib import admin

from api.models import ChapterIngestion, StoredPanel


class StoredPanelInline(admin.TabularInline):
    model = StoredPanel
    extra = 0
    readonly_fields = ("storage_key", "byte_size", "content_type", "public_url", "created_at")


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

from django.contrib import admin

from .models import CoverImage, RelationshipMap


@admin.register(CoverImage)
class CoverImageAdmin(admin.ModelAdmin):
    list_display = ("id", "work", "target_country", "is_representative", "created_at")
    list_filter = ("target_country", "is_representative")
    search_fields = ("work__title", "prompt")


@admin.register(RelationshipMap)
class RelationshipMapAdmin(admin.ModelAdmin):
    list_display = ("id", "work", "title", "created_at")
    search_fields = ("work__title", "title")


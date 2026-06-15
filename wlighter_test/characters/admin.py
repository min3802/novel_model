from django.contrib import admin

from .models import CharacterProfile


@admin.register(CharacterProfile)
class CharacterProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "work", "name", "role", "gender", "source", "updated_at")
    list_filter = ("source", "role", "gender")
    search_fields = ("name", "work__title", "relation", "appearance", "detail")


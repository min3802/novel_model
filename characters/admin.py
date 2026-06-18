from django.contrib import admin
from .models import Character


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ('char_name', 'work', 'role', 'gender', 'source', 'created_at')
    search_fields = ('char_name', 'work__title')
    list_filter = ('source', 'gender', 'role')
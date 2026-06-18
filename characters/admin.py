from django.contrib import admin

from .models import Character


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ('name', 'work', 'role', 'gender', 'source', 'updated_at')
    list_filter = ('source', 'gender', 'role')
    search_fields = ('name', 'work__title', 'relation', 'description')

from django.contrib import admin

from .models import RelationMap


@admin.register(RelationMap)
class RelationMapAdmin(admin.ModelAdmin):
    list_display = ('title', 'work', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'work__title')

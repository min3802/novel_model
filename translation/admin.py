from django.contrib import admin
from .models import TranslationResult, ChatMessage

admin.site.register(TranslationResult)
admin.site.register(ChatMessage)
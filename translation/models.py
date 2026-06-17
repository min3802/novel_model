from django.db import models
from works.models import Episode

class TranslationResult(models.Model):
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='translations')
    target_country = models.CharField(max_length=2)
    target_language = models.CharField(max_length=10)
    translated_text = models.TextField()
    review_summary = models.TextField(blank=True)
    final_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.episode} - {self.target_country}'


class ChatMessage(models.Model):
    translation = models.ForeignKey(TranslationResult, on_delete=models.CASCADE, related_name='chat_messages')
    sender_type = models.CharField(max_length=20)
    message_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.sender_type} - {self.translation}'
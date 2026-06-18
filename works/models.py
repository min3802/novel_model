from django.conf import settings
from django.db import models

class Work(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    pen_name = models.CharField(max_length=30, blank=True)
    genre = models.CharField(max_length=30)
    synopsis = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Episode(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='episodes')
    title = models.CharField(max_length=100)
    episode_no = models.PositiveIntegerField()
    original_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('work', 'episode_no')
        ordering = ['episode_no']

    def __str__(self):
        return f'{self.work.title} - {self.episode_no}화'
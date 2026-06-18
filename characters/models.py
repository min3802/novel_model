from django.db import models
from works.models import Work

class Character(models.Model):
    SOURCE_MANUAL = 'MANUAL'
    SOURCE_AI = 'AI'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, '수동 입력'),
        (SOURCE_AI, 'AI 추출'),
    ]

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='characters')
    name = models.CharField(max_length=50)
    role = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    age = models.CharField(max_length=20, blank=True)
    relation = models.TextField(blank=True)
    appearance = models.TextField(blank=True)
    personality = models.TextField(blank=True)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

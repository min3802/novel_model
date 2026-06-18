from django.db import models
from works.models import Work


class Character(models.Model):
    SOURCE_MANUAL = 'MANUAL'
    SOURCE_AI = 'AI'
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, '수동 입력'),
        (SOURCE_AI, 'AI 추출'),
    ]

    work = models.ForeignKey(
        Work,
        on_delete=models.CASCADE,
        related_name='characters'
    )

    char_name = models.CharField(max_length=30)
    age = models.CharField(max_length=10, blank=True)
    role = models.CharField(max_length=5, blank=True)
    gender = models.CharField(max_length=5, blank=True)
    relationships = models.CharField(max_length=500, blank=True)
    appearance = models.CharField(max_length=300, blank=True)
    detail_setting = models.CharField(max_length=1000, blank=True)

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.char_name
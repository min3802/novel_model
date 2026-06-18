from django.conf import settings
from django.db import models


class Cover(models.Model):
    work = models.ForeignKey('works.Work', on_delete=models.CASCADE, related_name='covers')
    cover_url = models.CharField(max_length=255)
    target_country = models.CharField(max_length=2, blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.work.title} 표지'


class CoverImage(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', '대기'
        SUCCESS = 'SUCCESS', '성공'
        FAILED = 'FAILED', '실패'
        BLOCKED = 'BLOCKED', '차단'

    class TargetCountry(models.TextChoices):
        US = 'US', '미국/영어권'
        CN = 'CN', '중국'
        JP = 'JP', '일본'
        TH = 'TH', '태국'

    work = models.ForeignKey('works.Work', on_delete=models.CASCADE, related_name='cover_images')
    title = models.CharField(max_length=100, blank=True)
    target_country = models.CharField(max_length=2, choices=TargetCountry.choices)
    genre = models.CharField(max_length=100, blank=True)
    synopsis_snapshot = models.TextField()
    synopsis_hash = models.CharField(max_length=64)
    user_prompt = models.CharField(max_length=500, blank=True)
    final_prompt = models.TextField(blank=True)
    image_path = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    model_name = models.CharField(max_length=50, default='gpt-image-2')
    prompt_version = models.CharField(max_length=50, default='cover_v1')
    credit_amount = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['work', 'target_country', 'is_deleted']),
            models.Index(fields=['created_by', 'is_deleted']),
        ]

    def __str__(self):
        return self.title or f'{self.work_id}-{self.target_country}-{self.created_at:%Y%m%d}'

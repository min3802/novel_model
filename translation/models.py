from django.db import models

from works.models import Episode


class TranslationResult(models.Model):
    """회차×대상국가 단위의 번역 버전(원문 스냅샷 + 번역본 쌍).

    REQ-CHAP-006/008: 번역 실행 시점의 원문(original_text)과 번역본을 한 버전으로
    동결 저장한다. (회차 × 대상국가)별 최대 3개 보관은 services.py에서 강제한다.
    """

    STATUS_DRAFT = 'DRAFT'
    STATUS_DONE = 'DONE'
    STATUS_BLOCKED = 'BLOCKED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, '작성중'),
        (STATUS_DONE, '완료'),
        (STATUS_BLOCKED, '안전성 차단'),
    ]

    episode = models.ForeignKey(
        Episode, on_delete=models.CASCADE, related_name='translations'
    )
    target_country = models.CharField(max_length=2)
    target_language = models.CharField(max_length=10, blank=True)
    version_no = models.PositiveIntegerField(default=1)

    original_text = models.TextField(blank=True)  # 번역 시점 원문 스냅샷
    translated_text = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    review_summary = models.TextField(blank=True)
    final_text = models.TextField(blank=True)

    glossary_can = models.JSONField(null=True, blank=True)
    annotation_can = models.JSONField(null=True, blank=True)
    inspection_report = models.JSONField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('episode', 'target_country', 'version_no')

    def __str__(self):
        return f'{self.episode} - {self.target_country} v{self.version_no}'


class ChatMessage(models.Model):
    SENDER_USER = 'USER'
    SENDER_ASSISTANT = 'ASSISTANT'
    SENDER_CHOICES = [
        (SENDER_USER, '사용자'),
        (SENDER_ASSISTANT, '챗봇'),
    ]

    translation = models.ForeignKey(
        TranslationResult, on_delete=models.CASCADE, related_name='chat_messages'
    )
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES)
    message_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender_type} - {self.translation}'

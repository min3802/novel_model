from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .constants import AI_IMAGE_NOTICE, COVER_IMAGE_LIMIT_PER_WORK, RELATION_MAP_LIMIT_PER_WORK, TARGET_COUNTRY_CHOICES


WORK_MODEL = getattr(settings, "WLIGHTER_WORK_MODEL", "works.Work")


class CoverImage(models.Model):
    work = models.ForeignKey(WORK_MODEL, on_delete=models.CASCADE, related_name="cover_images")
    target_country = models.CharField(max_length=2, choices=TARGET_COUNTRY_CHOICES)
    prompt = models.TextField()
    image_file = models.FileField(upload_to="wlighter/covers/%Y/%m/", blank=True)
    image_url = models.URLField(blank=True)
    is_representative = models.BooleanField(default=False)
    ai_notice = models.CharField(max_length=50, default=AI_IMAGE_NOTICE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        super().clean()
        count_query = CoverImage.objects.filter(work=self.work)
        if self.pk:
            count_query = count_query.exclude(pk=self.pk)
        if count_query.count() >= COVER_IMAGE_LIMIT_PER_WORK:
            raise ValidationError(f"작품당 표지 이미지는 최대 {COVER_IMAGE_LIMIT_PER_WORK}장까지 저장할 수 있습니다.")


class RelationshipMap(models.Model):
    work = models.ForeignKey(WORK_MODEL, on_delete=models.CASCADE, related_name="relationship_maps")
    title = models.CharField(max_length=80)
    relation_data = models.JSONField(default=dict)
    html_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        super().clean()
        count_query = RelationshipMap.objects.filter(work=self.work)
        if self.pk:
            count_query = count_query.exclude(pk=self.pk)
        if count_query.count() >= RELATION_MAP_LIMIT_PER_WORK:
            raise ValidationError(f"작품당 관계도는 최대 {RELATION_MAP_LIMIT_PER_WORK}개까지 저장할 수 있습니다.")


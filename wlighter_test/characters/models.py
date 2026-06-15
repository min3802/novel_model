from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from .constants import (
    AGE_MAX_LENGTH,
    APPEARANCE_MAX_LENGTH,
    CHARACTER_LIMIT_PER_WORK,
    DETAIL_MAX_LENGTH,
    GENDER_MAX_LENGTH,
    NAME_MAX_LENGTH,
    RELATION_MAX_LENGTH,
    ROLE_MAX_LENGTH,
)


WORK_MODEL = getattr(settings, "WLIGHTER_WORK_MODEL", "works.Work")


class CharacterProfile(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_AI = "ai"

    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "직접 등록"),
        (SOURCE_AI, "AI 생성"),
    )

    work = models.ForeignKey(
        WORK_MODEL,
        on_delete=models.CASCADE,
        related_name="character_profiles",
    )
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    age = models.CharField(max_length=AGE_MAX_LENGTH, blank=True)
    role = models.CharField(max_length=ROLE_MAX_LENGTH, blank=True)
    gender = models.CharField(max_length=GENDER_MAX_LENGTH, blank=True)
    relation = models.TextField(blank=True, validators=[MaxLengthValidator(RELATION_MAX_LENGTH)])
    appearance = models.TextField(blank=True, validators=[MaxLengthValidator(APPEARANCE_MAX_LENGTH)])
    detail = models.TextField(blank=True, validators=[MaxLengthValidator(DETAIL_MAX_LENGTH)])
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work", "name"], name="uniq_character_name_per_work"),
        ]
        ordering = ["name"]

    def clean(self):
        super().clean()
        if not self.name.strip():
            raise ValidationError({"name": "캐릭터 이름은 필수입니다."})

        count_query = CharacterProfile.objects.filter(work=self.work)
        if self.pk:
            count_query = count_query.exclude(pk=self.pk)
        if count_query.count() >= CHARACTER_LIMIT_PER_WORK:
            raise ValidationError(f"작품당 캐릭터는 최대 {CHARACTER_LIMIT_PER_WORK}명까지 등록할 수 있습니다.")

    def __str__(self):
        return self.name


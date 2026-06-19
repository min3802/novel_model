from django.db import models
from works.models import Work

class LocalizationGuide(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='localization_guides')
    # 시놉시스 기반 국가 추천 흐름에서는 국가가 비어 있을 수 있어 nullable (LOCALIZATIONGUIDES ERD).
    target_country = models.CharField(max_length=2, null=True, blank=True)
    guide_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.work.title} - {self.target_country or "(국가미정)"}'
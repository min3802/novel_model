from django.db import models
from works.models import Work

class LocalizationGuide(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='localization_guides')
    target_country = models.CharField(max_length=2)
    guide_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.work.title} - {self.target_country}'
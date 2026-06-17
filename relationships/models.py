from django.db import models
from works.models import Work

class RelationMap(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='relation_maps')
    title = models.CharField(max_length=100, default='관계도')
    html_content = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.work.title} - {self.title}'
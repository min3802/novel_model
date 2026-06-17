from django.db import models
from works.models import Work

class Character(models.Model):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='characters')
    name = models.CharField(max_length=50)
    role = models.CharField(max_length=30, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    age = models.CharField(max_length=20, blank=True)
    appearance = models.TextField(blank=True)
    personality = models.TextField(blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
from django import forms
from .models import Character


class CharacterForm(forms.ModelForm):
    class Meta:
        model = Character
        fields = [
            'char_name',
            'age',
            'role',
            'gender',
            'relationships',
            'appearance',
            'detail_setting',
        ]
        labels = {
            'char_name': '캐릭터 이름',
            'age': '나이',
            'role': '역할',
            'gender': '성별',
            'relationships': '관계',
            'appearance': '외형',
            'detail_setting': '세부 설정',
        }
        widgets = {
            'relationships': forms.Textarea(attrs={'rows': 4}),
            'appearance': forms.Textarea(attrs={'rows': 3}),
            'detail_setting': forms.Textarea(attrs={'rows': 6}),
        }
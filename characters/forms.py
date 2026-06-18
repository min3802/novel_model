from django import forms

from .models import Character


class CharacterForm(forms.ModelForm):
    class Meta:
        model = Character
        fields = ['name', 'role', 'gender', 'age', 'relation', 'appearance', 'personality', 'description']
        labels = {
            'name': '캐릭터 이름',
            'role': '역할',
            'gender': '성별',
            'age': '나이',
            'relation': '관계 요약',
            'appearance': '외형',
            'personality': '성격',
            'description': '설명',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '캐릭터 이름을 입력하세요.'}),
            'role': forms.TextInput(attrs={'placeholder': '주연, 조연, 단역 등'}),
            'gender': forms.TextInput(attrs={'placeholder': '성별을 입력하세요.'}),
            'age': forms.TextInput(attrs={'placeholder': '나이 또는 연령대를 입력하세요.'}),
            'relation': forms.Textarea(attrs={'placeholder': '다른 인물과의 관계를 입력하세요.', 'rows': 4}),
            'appearance': forms.Textarea(attrs={'placeholder': '외형 특징을 입력하세요.', 'rows': 4}),
            'personality': forms.Textarea(attrs={'placeholder': '성격과 말투를 입력하세요.', 'rows': 4}),
            'description': forms.Textarea(attrs={'placeholder': '캐릭터 설명을 입력하세요.', 'rows': 5}),
        }

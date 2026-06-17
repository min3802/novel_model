from django import forms

from .models import Episode, Work


class WorkForm(forms.ModelForm):
    class Meta:
        model = Work
        fields = ['title', 'pen_name', 'genre', 'synopsis']
        labels = {
            'title': '작품 제목',
            'pen_name': '필명',
            'genre': '장르',
            'synopsis': '시놉시스',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': '작품 제목을 입력하세요.'}),
            'pen_name': forms.TextInput(attrs={'placeholder': '필명을 입력하세요.'}),
            'genre': forms.TextInput(attrs={'placeholder': '장르를 입력하세요.'}),
            'synopsis': forms.Textarea(attrs={'placeholder': '작품 시놉시스를 입력하세요.', 'rows': 5}),
        }


class EpisodeForm(forms.ModelForm):
    class Meta:
        model = Episode
        fields = ['episode_no', 'title', 'original_text']
        labels = {
            'episode_no': '회차 번호',
            'title': '회차 제목',
            'original_text': '원문',
        }
        widgets = {
            'episode_no': forms.NumberInput(attrs={'placeholder': '회차 번호를 입력하세요.'}),
            'title': forms.TextInput(attrs={'placeholder': '회차 제목을 입력하세요.'}),
            'original_text': forms.Textarea(attrs={'placeholder': '회차 원문을 입력하세요.', 'rows': 12}),
        }

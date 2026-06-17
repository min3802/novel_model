from django import forms

from .prompts.cover_prompts import TARGET_COUNTRY_LABELS, USER_NOTICE_TEXT
from .validators.image_safety import MAX_USER_PROMPT_CHARS


class CoverImageCreateForm(forms.Form):
    target_country = forms.ChoiceField(
        label='대상 국가',
        choices=[(code, label) for code, label in TARGET_COUNTRY_LABELS.items()],
    )
    user_prompt = forms.CharField(
        label='추가 요청사항',
        required=False,
        max_length=MAX_USER_PROMPT_CHARS,
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': MAX_USER_PROMPT_CHARS}),
        help_text='최대 500자. 이번 이미지의 구도, 배경, 분위기, 표정 보완용입니다.',
    )
    image_size = forms.ChoiceField(
        label='이미지 크기',
        choices=[
            ('1024x1536', '세로형 1024x1536'),
            ('1024x1024', '정사각형 1024x1024'),
            ('1536x1024', '가로형 1536x1024'),
        ],
        initial='1024x1536',
    )

    notice_text = USER_NOTICE_TEXT

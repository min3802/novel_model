from django import forms

from .models import Profile
from .validators import validate_nickname


class ProfileUpdateForm(forms.ModelForm):
    """마이페이지 닉네임 수정 폼. 이메일/연동 제공자는 수정 불가 항목이라 제외."""

    class Meta:
        model = Profile
        fields = ['nickname']

    def clean_nickname(self):
        return validate_nickname(self.cleaned_data.get('nickname'))

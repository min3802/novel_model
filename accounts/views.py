from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileUpdateForm
from .models import Profile
from .services import withdraw_user


def _get_profile(user):
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={'nickname': (user.get_username() or 'user')[:10]},
    )
    return profile


def index(request):
    return render(request, 'accounts/index.html')


def login_view(request):
    # 실제 OAuth 로그인은 allauth 제공자 URL(/accounts/<provider>/login/)을 통해 진행.
    return render(request, 'accounts/login.html')


def logout_view(request):
    if request.method == 'POST':
        auth_logout(request)
        return redirect('accounts:login')
    return render(request, 'accounts/logout.html')


def signup(request):
    return render(request, 'accounts/signup.html')


@login_required
def profile_detail(request):
    profile = _get_profile(request.user)
    return render(
        request,
        'accounts/profile_detail.html',
        {'profile': profile, 'email': request.user.email},
    )


@login_required
def profile_update(request):
    profile = _get_profile(request.user)
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('accounts:profile_detail')
    else:
        form = ProfileUpdateForm(instance=profile)
    return render(
        request,
        'accounts/profile_update.html',
        {'form': form, 'profile': profile},
    )


@login_required
def withdraw(request):
    if request.method == 'POST':
        withdraw_user(request.user)
        auth_logout(request)
        return render(request, 'accounts/withdraw_done.html')
    return render(request, 'accounts/withdraw.html')

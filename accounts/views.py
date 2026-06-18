from django.shortcuts import render

def index(request):
    return render(request, 'accounts/index.html')


def login_view(request):
    return render(request, 'accounts/login.html')


def logout_view(request):
    return render(request, 'accounts/logout.html')


def signup(request):
    return render(request, 'accounts/signup.html')


def profile_detail(request):
    return render(request, 'accounts/profile_detail.html')


def profile_update(request):
    return render(request, 'accounts/profile_update.html')


def withdraw(request):
    return render(request, 'accounts/withdraw.html')

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include


def home(request):
    if request.user.is_authenticated:
        return redirect('works:work_list')
    return redirect('accounts:login')


urlpatterns = [
    path('', home, name='home'),

    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),
    path('works/', include('works.urls')),
    path('characters/', include('characters.urls')),
    path('translation/', include('translation.urls')),
    path('relationships/', include('relationships.urls')),
    path('covers/', include('covers.urls')),
    path('guides/', include('guides.urls')),
    path('credits/', include('credits.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
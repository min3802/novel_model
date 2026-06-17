from django.shortcuts import render

def index(request):
    return render(request, 'guides/index.html')


def guide_create(request):
    return render(request, 'guides/guide_create.html')


def guide_detail(request, guide_id):
    return render(request, 'guides/guide_detail.html', {'guide_id': guide_id})


def guide_download(request, guide_id):
    return render(request, 'guides/guide_download.html', {'guide_id': guide_id})


def guide_delete(request, guide_id):
    return render(request, 'guides/guide_delete.html', {'guide_id': guide_id})

from django.shortcuts import render

def index(request):
    return render(request, 'relationships/index.html')


def relation_create(request):
    return render(request, 'relationships/relation_create.html')


def relation_detail(request, map_id):
    return render(request, 'relationships/relation_detail.html', {'map_id': map_id})


def relation_download(request, map_id):
    return render(request, 'relationships/relation_download.html', {'map_id': map_id})


def relation_delete(request, map_id):
    return render(request, 'relationships/relation_delete.html', {'map_id': map_id})

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from works.models import Work

from .models import RelationMap
from .services.relation_html_generator import generate_relationship_map


@login_required
def relation_work_list(request):
    works = Work.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'relationships/relation_work_list.html', {'works': works})


@login_required
def relation_list(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    relation_maps = work.relation_maps.all().order_by('-created_at')
    characters = work.characters.all().order_by('id')
    return render(request, 'relationships/relation_list.html', {
        'work': work,
        'relation_maps': relation_maps,
        'characters': characters,
    })


@login_required
def relation_create(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    if request.method != 'POST':
        return redirect('relationships:relation_list', work_id=work.id)

    title = request.POST.get('title', '').strip()
    character_ids = request.POST.getlist('character_ids')

    try:
        relation_map = generate_relationship_map(work, title=title, character_ids=character_ids)
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
        return redirect('relationships:relation_list', work_id=work.id)
    except Exception as exc:
        messages.error(request, f'관계도 생성 실패: {exc}')
        return redirect('relationships:relation_list', work_id=work.id)

    messages.success(request, '관계도를 생성했습니다.')
    return redirect('relationships:relation_detail', work_id=work.id, map_id=relation_map.id)


@login_required
def relation_detail(request, work_id, map_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    relation_map = get_object_or_404(RelationMap, id=map_id, work=work)
    return render(request, 'relationships/relation_detail.html', {
        'work': work,
        'relation_map': relation_map,
    })


@login_required
def relation_html(request, work_id, map_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    relation_map = get_object_or_404(RelationMap, id=map_id, work=work)
    return HttpResponse(relation_map.html_content, content_type='text/html; charset=utf-8')


@login_required
def relation_download(request, work_id, map_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    relation_map = get_object_or_404(RelationMap, id=map_id, work=work)
    response = HttpResponse(relation_map.html_content, content_type='text/html; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="relation_map_{relation_map.id}.html"'
    return response


@login_required
def relation_delete(request, work_id, map_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    relation_map = get_object_or_404(RelationMap, id=map_id, work=work)

    if request.method == 'POST':
        relation_map.delete()
        messages.success(request, '관계도를 삭제했습니다.')
        return redirect('relationships:relation_list', work_id=work.id)

    return render(request, 'relationships/relation_delete.html', {
        'work': work,
        'relation_map': relation_map,
    })

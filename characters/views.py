from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from works.models import Work

from .forms import CharacterForm
from .models import Character


@login_required
def character_work_list(request):
    works = Work.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'characters/character_work_list.html', {'works': works})


@login_required
def character_list(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    characters = work.characters.all().order_by('name')
    return render(request, 'characters/character_list.html', {
        'work': work,
        'characters': characters,
    })


@login_required
def character_create(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)

    if request.method == 'POST':
        form = CharacterForm(request.POST)
        if form.is_valid():
            character = form.save(commit=False)
            character.work = work
            character.save()
            return redirect('characters:character_detail', work_id=work.id, character_id=character.id)
    else:
        form = CharacterForm()

    return render(request, 'characters/character_create.html', {
        'form': form,
        'work': work,
    })


@login_required
def character_detail(request, work_id, character_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    character = get_object_or_404(Character, id=character_id, work=work)
    return render(request, 'characters/character_detail.html', {
        'work': work,
        'character': character,
    })


@login_required
def character_update(request, work_id, character_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    character = get_object_or_404(Character, id=character_id, work=work)

    if request.method == 'POST':
        form = CharacterForm(request.POST, instance=character)
        if form.is_valid():
            form.save()
            return redirect('characters:character_detail', work_id=work.id, character_id=character.id)
    else:
        form = CharacterForm(instance=character)

    return render(request, 'characters/character_update.html', {
        'form': form,
        'work': work,
        'character': character,
    })


@login_required
def character_delete(request, work_id, character_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    character = get_object_or_404(Character, id=character_id, work=work)

    if request.method == 'POST':
        character.delete()
        return redirect('characters:character_list', work_id=work.id)

    return render(request, 'characters/character_delete.html', {
        'work': work,
        'character': character,
    })

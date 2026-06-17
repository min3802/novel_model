from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EpisodeForm, WorkForm
from .models import Episode, Work


@login_required
def work_list(request):
    works = Work.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'works/work_list.html', {'works': works})


@login_required
def work_create(request):
    if request.method == 'POST':
        form = WorkForm(request.POST)
        if form.is_valid():
            work = form.save(commit=False)
            work.user = request.user
            work.save()
            return redirect('works:work_detail', work_id=work.id)
    else:
        form = WorkForm()

    return render(request, 'works/work_create.html', {'form': form})


@login_required
def work_detail(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    episodes = work.episodes.all()
    return render(request, 'works/work_detail.html', {
        'work': work,
        'episodes': episodes,
    })


@login_required
def work_update(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)

    if request.method == 'POST':
        form = WorkForm(request.POST, instance=work)
        if form.is_valid():
            form.save()
            return redirect('works:work_detail', work_id=work.id)
    else:
        form = WorkForm(instance=work)

    return render(request, 'works/work_update.html', {
        'form': form,
        'work': work,
    })


@login_required
def work_delete(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)

    if request.method == 'POST':
        work.delete()
        return redirect('works:work_list')

    return render(request, 'works/work_delete.html', {'work': work})


@login_required
def episode_list(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    episodes = work.episodes.all()
    return render(request, 'works/episode_list.html', {
        'work': work,
        'episodes': episodes,
    })


@login_required
def episode_create(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)

    if request.method == 'POST':
        form = EpisodeForm(request.POST)
        if form.is_valid():
            episode = form.save(commit=False)
            episode.work = work
            episode.save()
            return redirect('works:episode_detail', work_id=work.id, episode_id=episode.id)
    else:
        form = EpisodeForm()

    return render(request, 'works/episode_create.html', {
        'form': form,
        'work': work,
    })


@login_required
def episode_detail(request, work_id, episode_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    episode = get_object_or_404(Episode, id=episode_id, work=work)
    return render(request, 'works/episode_detail.html', {
        'work': work,
        'episode': episode,
    })


@login_required
def episode_update(request, work_id, episode_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    episode = get_object_or_404(Episode, id=episode_id, work=work)

    if request.method == 'POST':
        form = EpisodeForm(request.POST, instance=episode)
        if form.is_valid():
            form.save()
            return redirect('works:episode_detail', work_id=work.id, episode_id=episode.id)
    else:
        form = EpisodeForm(instance=episode)

    return render(request, 'works/episode_update.html', {
        'form': form,
        'work': work,
        'episode': episode,
    })


@login_required
def episode_delete(request, work_id, episode_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    episode = get_object_or_404(Episode, id=episode_id, work=work)

    if request.method == 'POST':
        episode.delete()
        return redirect('works:episode_list', work_id=work.id)

    return render(request, 'works/episode_delete.html', {
        'work': work,
        'episode': episode,
    })

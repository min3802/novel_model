from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from works.models import Work

from .forms import CoverImageCreateForm
from .models import CoverImage
from .services.cover_generation import generate_cover_image
from .utils.file_utils import hash_text


def _media_url_from_path(path_text):
    if not path_text:
        return ''

    media_root = Path(settings.MEDIA_ROOT).resolve()
    image_path = Path(path_text).resolve()

    try:
        relative_path = image_path.relative_to(media_root)
    except ValueError:
        return path_text

    return f'{settings.MEDIA_URL}{relative_path.as_posix()}'


@login_required
def cover_work_list(request):
    works = Work.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'covers/cover_work_list.html', {'works': works})


@login_required
def cover_list(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)
    images = CoverImage.objects.filter(work=work, created_by=request.user, is_deleted=False)
    return render(request, 'covers/cover_list.html', {'work': work, 'images': images})


@login_required
def cover_create(request, work_id):
    work = get_object_or_404(Work, id=work_id, user=request.user)

    if request.method == 'POST':
        form = CoverImageCreateForm(request.POST)
        if form.is_valid():
            synopsis = work.synopsis or ''
            genre = work.genre or ''
            work_title = work.title or str(work)

            output_dir = Path(settings.MEDIA_ROOT) / 'cover_images' / str(work.id)
            result = generate_cover_image(
                work_title=work_title,
                genre=genre,
                synopsis=synopsis,
                target_country=form.cleaned_data['target_country'],
                user_prompt=form.cleaned_data.get('user_prompt', ''),
                output_dir=output_dir,
                size=form.cleaned_data.get('image_size') or '1024x1536',
                dry_run=False,
            )

            status = CoverImage.Status.FAILED
            if result.status == 'SUCCESS':
                status = CoverImage.Status.SUCCESS
            elif result.status == 'BLOCKED':
                status = CoverImage.Status.BLOCKED

            image = CoverImage.objects.create(
                work=work,
                title=f'{work_title} 커버 이미지',
                target_country=form.cleaned_data['target_country'],
                genre=genre,
                synopsis_snapshot=synopsis,
                synopsis_hash=hash_text(synopsis),
                user_prompt=form.cleaned_data.get('user_prompt', ''),
                final_prompt=result.final_prompt,
                image_path=_media_url_from_path(result.image_path),
                status=status,
                error_message='' if result.status == 'SUCCESS' else result.message,
                model_name=result.model_name,
                created_by=request.user,
            )

            if result.status == 'SUCCESS':
                messages.success(request, '커버 이미지가 생성되었습니다.')
            else:
                messages.error(request, result.message)

            return redirect(reverse('covers:cover_detail', kwargs={'work_id': work.id, 'image_id': image.id}))
    else:
        form = CoverImageCreateForm()

    return render(request, 'covers/cover_create.html', {'work': work, 'form': form})


@login_required
def cover_detail(request, work_id, image_id):
    image = get_object_or_404(
        CoverImage,
        id=image_id,
        work_id=work_id,
        created_by=request.user,
        is_deleted=False,
    )
    return render(request, 'covers/cover_detail.html', {'image': image, 'work': image.work})


@login_required
def cover_delete(request, work_id, image_id):
    image = get_object_or_404(
        CoverImage,
        id=image_id,
        work_id=work_id,
        created_by=request.user,
        is_deleted=False,
    )

    if request.method == 'POST':
        image.is_deleted = True
        image.save(update_fields=['is_deleted', 'updated_at'])
        messages.success(request, '커버 이미지를 삭제했습니다.')
        return redirect(reverse('covers:cover_list', kwargs={'work_id': work_id}))

    return render(request, 'covers/cover_delete.html', {'image': image, 'work': image.work})

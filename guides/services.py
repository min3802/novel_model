"""현지화 가이드 보관 로직 (REQ-GDE-001).

작품당 최대 5개 보관, 초과 시 가장 오래된 가이드 삭제.
"""

from .models import LocalizationGuide

MAX_GUIDES = 5


def create_guide(work, target_country, guide_content):
    guide = LocalizationGuide.objects.create(
        work=work,
        target_country=(target_country or None),
        guide_content=guide_content,
    )
    _enforce_cap(work)
    return guide


def _enforce_cap(work):
    qs = LocalizationGuide.objects.filter(work=work).order_by('-created_at')
    extra_ids = list(qs.values_list('id', flat=True)[MAX_GUIDES:])
    if extra_ids:
        LocalizationGuide.objects.filter(id__in=extra_ids).delete()

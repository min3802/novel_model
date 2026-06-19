"""번역 버전 관리 로직 (REQ-CHAP-006/008).

- (회차 × 대상국가)별 최대 3개 버전 보관, 초과 시 가장 오래된 버전 삭제.
- 원문이 변경되지 않은 단순 재실행은 새 버전을 만들지 않는다.
- 검수 챗봇 수정은 현재 버전을 갱신하며 새 버전을 만들지 않는다.
"""

from django.db import transaction

from .models import TranslationResult

MAX_VERSIONS = 3


def latest_version(episode, target_country):
    return (
        TranslationResult.objects.filter(episode=episode, target_country=target_country)
        .order_by('-version_no')
        .first()
    )


def source_unchanged(episode, target_country):
    latest = latest_version(episode, target_country)
    return latest is not None and latest.original_text == episode.original_text


@transaction.atomic
def create_translation_version(
    *,
    episode,
    target_country,
    translated_text,
    target_language='',
    summary='',
    review_summary='',
    glossary_can=None,
    annotation_can=None,
    inspection_report=None,
    status=TranslationResult.STATUS_DONE,
):
    """새 번역 버전을 생성한다.

    반환: (version, created) — 원문이 직전 버전과 동일하면 새 버전을 만들지 않고
    기존 최신 버전과 created=False를 반환한다.
    """
    latest = latest_version(episode, target_country)
    if latest is not None and latest.original_text == episode.original_text:
        return latest, False

    next_no = (latest.version_no + 1) if latest else 1
    version = TranslationResult.objects.create(
        episode=episode,
        target_country=target_country,
        version_no=next_no,
        original_text=episode.original_text,
        translated_text=translated_text,
        target_language=target_language,
        summary=summary,
        review_summary=review_summary,
        glossary_can=glossary_can,
        annotation_can=annotation_can,
        inspection_report=inspection_report,
        status=status,
    )
    _enforce_cap(episode, target_country)
    return version, True


def _enforce_cap(episode, target_country):
    qs = (
        TranslationResult.objects.filter(episode=episode, target_country=target_country)
        .order_by('-version_no')
    )
    extra_ids = list(qs.values_list('id', flat=True)[MAX_VERSIONS:])
    if extra_ids:
        # DB row 삭제(파일 삭제 아님). 보관 한도 초과 버전 정리(REQ-CHAP-006).
        TranslationResult.objects.filter(id__in=extra_ids).delete()


def apply_chat_edit(version, new_translated_text):
    """검수 챗봇 수정: 현재 버전 갱신, 새 버전 생성 안 함(REQ-CHAP-007)."""
    version.translated_text = new_translated_text
    version.final_text = new_translated_text
    version.save(update_fields=['translated_text', 'final_text', 'updated_at'])
    return version

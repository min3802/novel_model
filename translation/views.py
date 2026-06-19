from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from common import wlighter_client
from common.wlighter_client import COUNTRY_TO_LOCALE, WLighterServiceError
from works.models import Episode

from .models import ChatMessage, TranslationResult
from .services import apply_chat_edit, create_translation_version


def index(request):
    return render(request, 'translation/index.html')


def _owned_episode(request, episode_id):
    return get_object_or_404(Episode, pk=episode_id, work__user=request.user)


def _owned_translation(request, translation_id):
    return get_object_or_404(
        TranslationResult, pk=translation_id, episode__work__user=request.user
    )


def _map_response_to_fields(resp, country):
    delivery = resp.get('deliveryStatus', 'deliverable')
    blocked = delivery == 'blocked_translation_safety'
    internal = resp.get('internal') or {}
    rationale = resp.get('translationRationale') or {}
    return {
        'translated_text': '' if blocked else resp.get('finalTranslation', ''),
        'target_language': COUNTRY_TO_LOCALE.get(country, ''),
        'summary': rationale.get('overview', ''),
        'glossary_can': internal.get('entityCandidates') or internal.get('glossaryCandidateCapture'),
        'annotation_can': resp.get('readerEndnotes') or internal.get('characterReferences'),
        'inspection_report': {
            'deliveryStatus': delivery,
            'qaIssues': resp.get('qaIssues') or [],
            'authorReviewCards': resp.get('authorReviewCards') or [],
            'userVisibleErrorCode': internal.get('userVisibleErrorCode'),
        },
        'status': TranslationResult.STATUS_BLOCKED if blocked else TranslationResult.STATUS_DONE,
    }


@login_required
def translation_run(request, episode_id):
    episode = _owned_episode(request, episode_id)
    if request.method == 'POST':
        country = (request.POST.get('target_country') or '').upper()
        if country not in COUNTRY_TO_LOCALE:
            messages.error(request, '지원하는 대상 국가는 US/CN/JP/TH 입니다.')
            return redirect('translation:translation_run', episode_id=episode_id)
        try:
            resp = wlighter_client.translate(
                source_text=episode.original_text,
                target_country=country,
                work_id=episode.work_id,
                episode_id=episode.id,
                genre=episode.work.genre,
            )
        except WLighterServiceError as exc:
            messages.error(request, f'번역 서비스 호출에 실패했습니다: {exc}')
            return redirect('translation:translation_run', episode_id=episode_id)

        fields = _map_response_to_fields(resp, country)
        version, created = create_translation_version(
            episode=episode, target_country=country, **fields
        )
        if not created:
            messages.info(request, '원문이 변경되지 않아 기존 번역 버전을 유지합니다.')
        return redirect(
            'translation:translation_version_list', episode_id=episode_id
        )
    return render(request, 'translation/translation_run.html', {'episode': episode})


@login_required
def translation_version_list(request, episode_id):
    episode = _owned_episode(request, episode_id)
    versions = episode.translations.all().order_by('target_country', '-version_no')
    return render(
        request,
        'translation/translation_version_list.html',
        {'episode': episode, 'versions': versions},
    )


@login_required
def review_chatbot(request, translation_id):
    translation = _owned_translation(request, translation_id)
    if request.method == 'POST':
        text = (request.POST.get('message') or '').strip()
        if not text:
            messages.error(request, '메시지를 입력해 주세요.')
        elif len(text) > 1000:
            messages.error(request, '메시지는 최대 1,000자까지 입력할 수 있습니다.')
        else:
            ChatMessage.objects.create(
                translation=translation,
                sender_type=ChatMessage.SENDER_USER,
                message_text=text,
            )
            try:
                history = list(
                    translation.chat_messages.values('sender_type', 'message_text')
                )
                resp = wlighter_client.inspect_chat(
                    message=text,
                    translation_id=translation.id,
                    context={
                        'translatedText': translation.translated_text,
                        'targetCountry': translation.target_country,
                    },
                    history=history,
                )
                reply = resp.get('reply') or resp.get('message') or ''
                ChatMessage.objects.create(
                    translation=translation,
                    sender_type=ChatMessage.SENDER_ASSISTANT,
                    message_text=reply,
                )
                proposed = resp.get('proposedTranslation') or resp.get('proposed_translation')
                if proposed and request.POST.get('apply') == '1':
                    # 챗봇 수정 반영: 현재 버전 갱신(새 버전 생성 안 함)
                    apply_chat_edit(translation, proposed)
            except WLighterServiceError as exc:
                messages.error(request, f'검수 챗봇 호출에 실패했습니다: {exc}')
        return redirect('translation:review_chatbot', translation_id=translation_id)

    chat_messages = translation.chat_messages.all()
    return render(
        request,
        'translation/review_chatbot.html',
        {'translation': translation, 'chat_messages': chat_messages},
    )


@login_required
def translation_version_delete(request, translation_id):
    translation = _owned_translation(request, translation_id)
    episode_id = translation.episode_id
    if request.method == 'POST':
        translation.delete()
        messages.success(request, '번역 버전을 삭제했습니다.')
        return redirect('translation:translation_version_list', episode_id=episode_id)
    return render(
        request,
        'translation/translation_version_delete.html',
        {'translation': translation},
    )

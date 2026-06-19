"""FastAPI 번역/현지화 서비스(`모델링 작업_통합 초안/api_server.py`) HTTP 클라이언트.

Django translation/guides 앱이 이 모듈을 통해 외부 번역 서비스와 통신한다.
서비스 base URL은 settings.WLIGHTER_API_BASE(기본 http://127.0.0.1:8001)에서 읽는다.
서버 미가동/오류는 WLighterServiceError로 감싸 안전하게 실패한다(번역 자체를 죽이지 않음).
"""

from __future__ import annotations

import requests
from django.conf import settings

# UI/DB country code <-> v3 엔진 locale (translation_api_contract.md 기준)
COUNTRY_TO_LOCALE = {
    'US': 'ko_en_us',
    'CN': 'ko_zh_cn',
    'JP': 'ko_ja',
    'TH': 'ko_th_th',
}
LOCALE_TO_COUNTRY = {locale: country for country, locale in COUNTRY_TO_LOCALE.items()}

DEFAULT_TIMEOUT = 120


class WLighterServiceError(Exception):
    """외부 번역 서비스 호출 실패."""


def base_url() -> str:
    url = getattr(settings, 'WLIGHTER_API_BASE', '') or 'http://127.0.0.1:8001'
    return url.rstrip('/')


def _post(path: str, payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    url = base_url() + path
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:  # 연결 실패/타임아웃/HTTP 에러 등
        raise WLighterServiceError(f'{path} 호출 실패: {exc}') from exc
    except ValueError as exc:  # JSON 파싱 실패
        raise WLighterServiceError(f'{path} 응답 파싱 실패: {exc}') from exc


def translate(*, source_text, target_country, work_id=None, episode_id=None, genre=None, timeout=DEFAULT_TIMEOUT):
    payload = {'sourceText': source_text, 'targetCountry': target_country}
    if work_id is not None:
        payload['workId'] = str(work_id)
    if episode_id is not None:
        payload['episodeId'] = str(episode_id)
    if genre:
        payload['genre'] = genre
    return _post('/api/translate', payload, timeout=timeout)


def generate_guide(*, target_country=None, genre=None, synopsis=None, work_id=None, timeout=DEFAULT_TIMEOUT):
    payload = {}
    if target_country is not None:
        payload['targetCountry'] = target_country
    if genre:
        payload['genre'] = genre
    if synopsis is not None:
        payload['synopsis'] = synopsis
    if work_id is not None:
        payload['workId'] = str(work_id)
    return _post('/api/guide', payload, timeout=timeout)


def inspect_chat(*, message, translation_id=None, context=None, history=None, timeout=DEFAULT_TIMEOUT):
    payload = {'message': message}
    if translation_id is not None:
        payload['translationId'] = str(translation_id)
    if context is not None:
        payload['context'] = context
    if history is not None:
        payload['history'] = history
    return _post('/api/inspect-chat', payload, timeout=timeout)

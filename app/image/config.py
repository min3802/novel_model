from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImageConfig:
    """이미지 기능(추출·생성) 공통 설정.

    번역 쪽 PipelineConfig 와 동일한 패턴(dataclass 로 모델명·파라미터 관리)을 따른다.

    표지(cover)와 관계도(relation)는 요구사항상 별개 플로우다.
    - 표지:   REQ-IMG-001/002/003, TST-IMG-001, /api/generate-cover-image
    - 관계도: REQ-IMG-004/005/006, TST-IMG-002, /api/generate-relation-image
    각 플로우는 자기 정보만 추출→생성하고, 끝나면 추출 정보는 휘발한다.
    """

    # --- ① 추출 LLM (표지/관계도 공통 모델, 순수 추출이라 미니로 충분) ----
    extract_model: str = "gpt-4.1-mini"

    # 추출은 원문만 보면 되는 순수 작업이라 기본은 RAG 미사용.
    # 추후 한국 문화 맥락(호칭/신분 등) 보강이 필요하면 True 로 켜고 kculture RAG 연결.
    # (현재 use_rag=True 경로는 미구현 — 확장 지점만 남겨둔다.)
    use_rag: bool = False

    # 추출 입력 분량 상한 (요구사항: 표지 최대 10화, 관계도 최대 20화).
    # 관계는 누적할수록 풍부하므로 관계도 쪽이 더 길다.
    cover_max_episodes: int = 10
    relation_max_episodes: int = 20

    # 화당 입력 글자 보호 상한(과도한 토큰 방지). 초과 시 뒤쪽(최신) 우선 보존.
    max_input_chars: int = 40000

    # --- ② 생성(cover_generator / relation_generator) ----------------
    image_model: str = "gpt-image-2"
    image_size: str = "1024x1024"

    # 표지에 등장시킬 주요 인물 수(주인공 1명 기본). 사용자가 추가 프롬프트로 조정 가능.
    cover_subject_count: int = 1

    # --- 안전검사(표지 전용) -----------------------------------------
    # 부적절 시각 요청을 LLM 으로 "거부 + 대안 제시" 생성. mock 시 고정 메시지.
    safety_model: str = "gpt-4.1-mini"

    # 공통 안내 문구.
    ai_notice: str = "AI 생성 이미지입니다."

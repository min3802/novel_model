# w.LiGHTER Translation Consistency Streamlit Test App

## 목적
기존 번역 코어를 최대한 유지한 상태에서 다음 흐름을 확인하는 테스트용 앱입니다.

1. 원문 회차를 읽는다.
2. 기존 glossary/user_overrides 중 이번 회차에 실제 등장한 항목만 번역 프롬프트에 주입한다.
3. 번역을 실행한다.
4. 번역 결과의 translation_decisions를 기반으로 glossary/translation_memory/consistency_report를 저장한다.
5. 챗봇으로 번역을 수정한다.
6. 사용자가 승인한 수정 표현을 user_overrides.json에 저장한다.
7. 다음 회차 번역에서 user_overrides가 glossary보다 우선 적용되는지 확인한다.

## 실행
프로젝트 루트에서 실행합니다.

```bat
streamlit run app.py
```

`.env` 파일은 별도로 포함하지 않았습니다. 직접 아래 값을 넣어 사용하면 됩니다.

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
# 선택
OPENAI_TRANSLATION_MODEL=gpt-4.1-mini
OPENAI_REVIEW_MODEL=gpt-4.1-mini
WLIGHTER_MEDIA_ROOT=D:\Final_project\media\works
```

## 기본 모델 선택
기본 추천은 `gpt-4.1-mini`입니다.

이유:
- 지금 테스트의 핵심은 최고 품질 번역이 아니라 번역 일관성 데이터의 저장/재사용/사용자 수정 반영입니다.
- glossary/user_overrides가 확정 표현을 강제하므로, 매 회차마다 무거운 모델을 쓸 필요가 줄어듭니다.
- `gpt-5-mini`는 관계/추론이 필요한 복잡한 검수에는 유리할 수 있지만, 현재 앱 테스트에서는 속도와 비용 부담이 큽니다.
- UI에서 모델을 바꿀 수 있으므로, 1~2화는 4.1-mini로 돌리고 비교용으로만 5-mini를 사용하면 됩니다.

## 포함된 테스트 원문
아래 경로에 야구소설 5편을 넣어두었습니다.

```text
media/works/WORK_001/uploads/episode_001.txt
media/works/WORK_001/uploads/episode_002.txt
media/works/WORK_001/uploads/episode_003.txt
media/works/WORK_001/uploads/episode_004.txt
media/works/WORK_001/uploads/episode_005.txt
```

## 생성되는 파일

```text
media/works/WORK_001/translated/episode_001_ko_en_us.txt
media/works/WORK_001/translation_consistency/glossary.json
media/works/WORK_001/translation_consistency/translation_memory.json
media/works/WORK_001/translation_consistency/user_overrides.json
media/works/WORK_001/translation_consistency/chat_edits.json
media/works/WORK_001/translation_consistency/consistency_report_EP_001_ko_en_us.json
```

## 이번 버전에서 의도적으로 제외한 것
- 문체 일관성 자동 분석
- 번역 전 대규모 setting_book 생성
- 관계도/온톨로지 대량 추출
- 야구 장르 기반 하드코딩

현재 목표는 고유명사, 팀/조직/장소, 반복 용어, 사용자 수정 표현의 일관성입니다.

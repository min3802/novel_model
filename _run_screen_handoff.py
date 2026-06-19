"""화면설계 팀 인계용: 번역 파이프라인(v3_literary_package) 1회 라이브 실행 → 응답 JSON 저장.

실행: (모델링 작업_통합 초안 폴더에서)
    python _run_screen_handoff.py
일회성 헬퍼라 실행 후 삭제해도 무방하다.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["WLIGHTER_MOCK_MODE"] = "false"  # 라이브 강제

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception as exc:  # noqa: BLE001
    print(f"[warn] load_dotenv 실패: {exc!r}")

SRC = ROOT.parent / "소설_모음" / "학원학교물_1.txt"
OUT_JSON = ROOT / "outputs" / "screen_handoff_학원학교물_1_ko_en_us.json"


def main() -> int:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        print("[FAIL] OPENAI_API_KEY 없음")
        return 1
    if not SRC.exists():
        print(f"[FAIL] 원문 없음: {SRC}")
        return 1

    source_text = SRC.read_text(encoding="utf-8")
    print(f"[입력] {SRC.name} {len(source_text)}자 읽음")

    from backend.services.translation_service import translate

    payload = {"sourceText": source_text, "targetLocale": "ko_en_us"}
    print("[실행] translate() v3_literary_package 라이브 호출 시작...")
    t0 = time.time()
    result = translate(payload)
    elapsed = time.time() - t0
    print(f"[완료] {elapsed:.1f}s")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 요약 진단
    def filled(v) -> str:
        if v is None:
            return "None"
        if isinstance(v, (list, dict, str)):
            return "O" if len(v) > 0 else "(빈값)"
        return "O"

    print("\n===== 응답 top-level 필드 =====")
    for k, v in result.items():
        tn = type(v).__name__
        print(f"  {k:24s} {tn:6s} {filled(v)}")

    print("\n===== 핵심 값 =====")
    print(f"  deliveryStatus     : {result.get('deliveryStatus')}")
    print(f"  userVisibleError   : {result.get('userVisibleErrorCode')}")
    ft = result.get("finalTranslation") or ""
    print(f"  finalTranslation   : ({len(ft)}자) {ft[:300]}")
    cards = result.get("authorReviewCards") or []
    print(f"  authorReviewCards  : {len(cards)}건")
    qa = result.get("qaIssues") or []
    print(f"  qaIssues           : {len(qa)}건")
    rationale = result.get("translationRationale") or {}
    print(f"  translationRationale items: {len((rationale.get('items') or []))}")
    internal = result.get("internal") or {}
    print(f"  internal keys      : {list(internal.keys())}")
    print(f"\n[저장] {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

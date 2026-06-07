"""
qdrant end-to-end 연결 진단 스크립트.

실행:  (프로젝트 루트 = 이 파일이 있는 폴더에서)
    python tests/check_qdrant_e2e.py

무엇을 확인하나:
  1) sentence-transformers / KURE 모델이 설치·로딩되는가
  2) qdrant_local 에 붙어서 컬렉션이 보이는가
  3) "한국어 문장 -> KURE 임베딩 -> qdrant 검색" 전체 경로가 도는가  (mock=False)
  4) AnnotationRetriever(kculture) 도 동일하게 도는가
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# 이 스크립트는 tests/ 안에 있지만, 프로젝트 루트의 app.translation 을 import 해야 한다.
# 어디서 실행하든(루트/ tests 폴더 등) 동작하도록 루트를 sys.path 에 추가한다.
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import sys
import time

OK = "[OK]"
NO = "[FAIL]"


def step(title: str) -> None:
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main() -> int:
    import os
    os.environ["WLIGHTER_MOCK_MODE"] = "false"  # 실 경로(qdrant)로 강제

    # .env 로드 (HF_TOKEN, OPENAI_API_KEY 등). KURE 로딩 전에 먼저 실행되어야 한다.
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except Exception:
        pass

    step("1) sentence-transformers / KURE 설치 확인")
    try:
        import sentence_transformers
        print(f"{OK} sentence-transformers 설치됨 (v{sentence_transformers.__version__})")
    except ImportError:
        print(f"{NO} sentence-transformers 가 없습니다.  설치:  pip install sentence-transformers")
        return 1

    step("2) qdrant_local 연결 / 컬렉션 확인")
    try:
        from app.translation.config import PipelineConfig
        from app.translation.retrieval.retriever import make_qdrant_client
    except Exception as exc:
        print(f"{NO} 패키지 import 실패: {exc!r}")
        return 1
    cfg = PipelineConfig(locale="ko_ja")
    try:
        client = make_qdrant_client(cfg)
        cols = [c.name for c in client.get_collections().collections]
        print(f"{OK} qdrant 연결 성공. 컬렉션: {cols}")
        print(f"   qdrant 경로: {cfg.resolved_qdrant_path()}")
    except Exception as exc:
        print(f"{NO} qdrant 연결 실패: {exc!r}")
        return 1

    step("3) IdiomRetriever end-to-end (한국어 문장 -> KURE -> qdrant)")
    sample = "자업자득이라더니, 결국 본인이 한 행동의 결과를 받는 거지."
    try:
        from app.translation.retrieval.idiom_retriever import IdiomRetriever
        print("   KURE 모델 로딩 중... (처음 1회는 수 초~수십 초 소요)")
        t0 = time.time()
        retriever = IdiomRetriever(cfg)
        print(f"   로딩 완료 ({time.time()-t0:.1f}s)")
        t1 = time.time()
        results = retriever.retrieve(sample, top_k=3)
        print(f"{OK} 검색 완료 ({time.time()-t1:.2f}s), 결과 {len(results)}건")
        for i, r in enumerate(results, 1):
            it = r.item
            print(f"   {i}. score={r.similarity_score:.4f}  id={it.get('source_id')}  {str(it.get('embedding_text',''))[:40]}")
        if not results:
            print(f"   (주의: 결과 0건 — score_threshold={cfg.score_threshold} 보다 높은 게 없을 수 있음)")
    except Exception as exc:
        print(f"{NO} end-to-end 실패: {exc!r}")
        return 1

    step("4) AnnotationRetriever end-to-end (kculture)")
    sample2 = "그 사람 당근으로 중고 거래한다더라."
    try:
        from app.translation.retrieval.annotation_retriever import AnnotationRetriever
        anno = AnnotationRetriever(cfg)
        res2 = anno.retrieve(sample2, top_k=3)
        print(f"{OK} 주석 검색 완료, 결과 {len(res2)}건")
        for i, r in enumerate(res2, 1):
            it = r.item
            print(f"   {i}. score={r.similarity_score:.4f}  keyword={it.get('keyword_ko')}  category={it.get('category')}")
    except Exception as exc:
        print(f"{NO} annotation 검색 실패: {exc!r}")
        return 1

    step("결과")
    print(f"{OK} 전체 통과 — qdrant + KURE end-to-end 정상 작동.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

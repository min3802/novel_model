def relationship_html_to_pdf_bytes(html_content: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("PDF 다운로드를 사용하려면 weasyprint 설치가 필요합니다.") from exc
    return HTML(string=html_content).write_pdf()


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from common import wlighter_client
from common.wlighter_client import COUNTRY_TO_LOCALE, WLighterServiceError
from works.models import Work

from .models import LocalizationGuide
from .services import create_guide


def index(request):
    return render(request, 'guides/index.html')


def _extract_guide_content(resp):
    for key in ('guideContent', 'guide_content', 'guide', 'content', 'finalGuide', 'text'):
        value = resp.get(key)
        if value:
            return value if isinstance(value, str) else str(value)
    return ''


@login_required
def guide_create(request):
    if request.method == 'POST':
        work = get_object_or_404(
            Work, pk=request.POST.get('work_id'), user=request.user
        )
        country = (request.POST.get('target_country') or '').upper() or None
        if country and country not in COUNTRY_TO_LOCALE:
            messages.error(request, '지원하는 대상 국가는 US/CN/JP/TH 입니다.')
            return redirect('guides:guide_create')
        # 시놉시스가 없으면 국가 직접 선택 필요(REQ-GDE-001 모드 B)
        if not work.synopsis and not country:
            messages.error(request, '시놉시스가 없는 작품은 대상 국가를 직접 선택해야 합니다.')
            return redirect('guides:guide_create')
        try:
            resp = wlighter_client.generate_guide(
                target_country=country,
                genre=work.genre,
                synopsis=work.synopsis or None,
                work_id=work.id,
            )
        except WLighterServiceError as exc:
            messages.error(request, f'가이드 생성 서비스 호출에 실패했습니다: {exc}')
            return redirect('guides:guide_create')

        content = _extract_guide_content(resp)
        # 시놉시스 기반 추천 모드에서 서비스가 국가를 돌려줄 수 있음
        resolved_country = country or (resp.get('targetCountry') or resp.get('recommendedCountry'))
        guide = create_guide(work, resolved_country, content)
        return redirect('guides:guide_detail', guide_id=guide.id)

    works = Work.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'guides/guide_create.html', {'works': works})


@login_required
def guide_detail(request, guide_id):
    guide = get_object_or_404(
        LocalizationGuide, pk=guide_id, work__user=request.user
    )
    return render(request, 'guides/guide_detail.html', {'guide': guide})


@login_required
def guide_download(request, guide_id):
    guide = get_object_or_404(
        LocalizationGuide, pk=guide_id, work__user=request.user
    )
    # 요청 시점에 생성, 파일 자체는 저장하지 않음(REQ-GDE-004).
    # 정식 PDF 생성 라이브러리(reportlab 등)가 설치돼 있으면 PDF로, 아니면 텍스트로 폴백.
    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        text_obj = pdf.beginText(40, 800)
        for line in (guide.guide_content or '').splitlines() or ['']:
            text_obj.textLine(line[:120])
        pdf.drawText(text_obj)
        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="guide-{guide.id}.pdf"'
        return response
    except ImportError:
        # PDF 라이브러리 미설치 → 텍스트 폴백 (미완_작업.md 참고)
        response = HttpResponse(guide.guide_content, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="guide-{guide.id}.txt"'
        return response


@login_required
def guide_delete(request, guide_id):
    guide = get_object_or_404(
        LocalizationGuide, pk=guide_id, work__user=request.user
    )
    if request.method == 'POST':
        guide.delete()
        messages.success(request, '현지화 가이드를 삭제했습니다.')
        return redirect('guides:index')
    return render(request, 'guides/guide_delete.html', {'guide': guide})

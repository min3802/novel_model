import base64
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from characters.models import CharacterProfile

from ..constants import COVER_IMAGE_LIMIT_PER_WORK, EXTRA_PROMPT_MAX_LENGTH
from ..models import CoverImage
from .openai_client import get_image_model, get_image_size, get_openai_client


COUNTRY_GUIDE = {
    "JP": "Japanese web novel market, clean commercial light-novel cover readability",
    "CN": "Chinese online fiction market, dramatic composition with strong genre signal",
    "US": "US web fiction market, cinematic readable thumbnail and clear protagonist hook",
    "TH": "Thai web novel market, polished romantic/dramatic web fiction cover readability",
}


def first_attr(obj, names, default="") -> str:
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return str(value)
    return default


def build_cover_prompt(work, target_country: str, extra_prompt: str = "") -> str:
    characters = list(CharacterProfile.objects.filter(work=work).order_by("id")[:5])
    character_text = "\n".join(
        [
            (
                f"- {c.name}: role={c.role or '-'}, gender={c.gender or '-'}, age={c.age or '-'}, "
                f"appearance={c.appearance or '-'}, detail={c.detail or '-'}, relation={c.relation or '-'}"
            )
            for c in characters
        ]
    )

    return f"""
Create a vertical commercial web novel cover illustration.

Work title: {first_attr(work, ["title", "name"], "작품")}
Genre: {first_attr(work, ["genre"], "web novel")}
Target market: {COUNTRY_GUIDE.get(target_country, "global web novel market")}
Synopsis: {first_attr(work, ["synopsis", "description", "desc"], "")[:1200] or "No synopsis provided."}

Character settings:
{character_text or "- No character settings registered yet. Use synopsis and genre only."}

Additional user request:
{extra_prompt.strip() or "No additional request."}

Requirements:
- Use the registered character settings as the primary source.
- Make one clear focal composition suitable for a cover thumbnail.
- Family-friendly, non-sexual, safe-for-all-ages.
- No generated text, logos, signatures, or watermarks.
- Avoid real public figure resemblance.
""".strip()


def generate_cover_image(work, target_country: str, extra_prompt: str = "") -> CoverImage:
    if len(extra_prompt or "") > EXTRA_PROMPT_MAX_LENGTH:
        raise ValidationError(f"추가 요청 문구는 최대 {EXTRA_PROMPT_MAX_LENGTH}자까지 입력할 수 있습니다.")
    if CoverImage.objects.filter(work=work).count() >= COVER_IMAGE_LIMIT_PER_WORK:
        raise ValidationError(f"작품당 표지 이미지는 최대 {COVER_IMAGE_LIMIT_PER_WORK}장까지 저장할 수 있습니다.")

    prompt = build_cover_prompt(work, target_country, extra_prompt)
    response = get_openai_client().images.generate(
        model=get_image_model(),
        prompt=prompt,
        size=get_image_size(),
        n=1,
    )
    item = response.data[0]
    b64_json = getattr(item, "b64_json", None)
    image_url = getattr(item, "url", None)

    image = CoverImage(work=work, target_country=target_country, prompt=prompt)
    if b64_json:
        image.image_file.save(
            f"cover_{work.pk}_{uuid4().hex}.png",
            ContentFile(base64.b64decode(b64_json)),
            save=False,
        )
    elif image_url:
        image.image_url = image_url
    else:
        raise RuntimeError("이미지 생성 결과에서 이미지 데이터를 찾지 못했습니다.")

    image.full_clean()
    image.save()
    return image


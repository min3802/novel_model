import os

from django.conf import settings


def get_openai_client():
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
    return OpenAI(api_key=api_key)


def get_image_model() -> str:
    return getattr(settings, "WLIGHTER_IMAGE_MODEL", os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"))


def get_image_size() -> str:
    return getattr(settings, "WLIGHTER_IMAGE_SIZE", os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"))


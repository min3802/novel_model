import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


class OpenAIClientError(RuntimeError):
    pass


@dataclass
class ImageGenerationResponse:
    image_base64: str
    model_name: str


def _load_env():
    if load_dotenv is not None:
        load_dotenv()


def _get_api_key():
    _load_env()
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise OpenAIClientError('OPENAI_API_KEY 환경변수가 없습니다.')
    return api_key


def get_openai_client():
    try:
        from openai import OpenAI
    except Exception as exc:
        raise OpenAIClientError(f'openai 패키지를 불러오지 못했습니다: {exc}') from exc

    return OpenAI(api_key=_get_api_key())


def generate_image_base64(*, prompt, model_name='gpt-image-2', size='1024x1536', quality='auto', output_format='png'):
    client = get_openai_client()

    try:
        response = client.images.generate(
            model=model_name,
            prompt=prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            n=1,
        )
    except Exception as exc:
        raise OpenAIClientError(f'이미지 생성 API 호출 실패: {exc}') from exc

    image_data = response.data[0]
    image_base64 = getattr(image_data, 'b64_json', None) or getattr(image_data, 'image_base64', None)
    if not image_base64:
        raise OpenAIClientError('이미지 base64 응답을 찾지 못했습니다.')

    return ImageGenerationResponse(
        image_base64=image_base64,
        model_name=model_name,
    )

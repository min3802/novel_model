from dataclasses import asdict, dataclass
from pathlib import Path

from common.openai_client import OpenAIClientError, generate_image_base64
from covers.prompts.cover_prompts import build_cover_prompt
from covers.validators.image_safety import ImageInputValidationError, assert_valid_cover_inputs
from covers.utils.file_utils import ensure_dir, hash_text, now_stamp, safe_filename, save_base64_file, save_json, save_text

DEFAULT_IMAGE_MODEL = 'gpt-image-2'
DEFAULT_IMAGE_SIZE = '1024x1536'
DEFAULT_IMAGE_QUALITY = 'auto'
DEFAULT_OUTPUT_FORMAT = 'png'


@dataclass
class CoverPromptPayload:
    work_title: str
    genre: str
    synopsis: str
    target_country: str
    user_prompt: str
    final_prompt: str
    synopsis_hash: str
    prompt_version: str = 'cover_v1'


@dataclass
class CoverGenerationResult:
    status: str
    image_path: str | None
    prompt_path: str
    metadata_path: str
    final_prompt: str
    model_name: str
    size: str
    quality: str
    output_format: str
    message: str = ''


def build_cover_payload(*, work_title, genre, synopsis, target_country, user_prompt=''):
    country = target_country.strip().upper()
    assert_valid_cover_inputs(
        synopsis=synopsis,
        target_country=country,
        user_prompt=user_prompt,
    )
    final_prompt = build_cover_prompt(
        work_title=work_title,
        genre=genre,
        synopsis=synopsis,
        target_country=country,
        user_prompt=user_prompt,
    )
    return CoverPromptPayload(
        work_title=work_title.strip(),
        genre=genre.strip(),
        synopsis=synopsis.strip(),
        target_country=country,
        user_prompt=user_prompt.strip(),
        final_prompt=final_prompt,
        synopsis_hash=hash_text(synopsis),
    )


def save_prompt_payload(payload, output_dir):
    out = ensure_dir(output_dir)
    stamp = now_stamp()
    prefix = f'cover_{safe_filename(payload.work_title)}_{payload.target_country}_{stamp}'
    prompt_path = save_text(payload.final_prompt, out / f'{prefix}_prompt.txt')
    metadata_path = save_json(asdict(payload), out / f'{prefix}_metadata.json')
    return {'prompt_path': prompt_path, 'metadata_path': metadata_path}


def _failed_result(*, status, message, model_name, size, quality, output_format, final_prompt=''):
    return CoverGenerationResult(
        status=status,
        image_path=None,
        prompt_path='',
        metadata_path='',
        final_prompt=final_prompt,
        model_name=model_name,
        size=size,
        quality=quality,
        output_format=output_format,
        message=message,
    )


def generate_cover_image(
    *,
    work_title,
    genre,
    synopsis,
    target_country,
    user_prompt='',
    output_dir='media/cover_images',
    model_name=DEFAULT_IMAGE_MODEL,
    size=DEFAULT_IMAGE_SIZE,
    quality=DEFAULT_IMAGE_QUALITY,
    output_format=DEFAULT_OUTPUT_FORMAT,
    dry_run=False,
):
    try:
        payload = build_cover_payload(
            work_title=work_title,
            genre=genre,
            synopsis=synopsis,
            target_country=target_country,
            user_prompt=user_prompt,
        )
    except ImageInputValidationError as exc:
        return _failed_result(
            status='BLOCKED',
            message=str(exc),
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
        )
    except Exception as exc:
        return _failed_result(
            status='FAILED',
            message=f'프롬프트 생성 실패: {exc}',
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
        )

    saved = save_prompt_payload(payload, output_dir)

    if dry_run:
        return CoverGenerationResult(
            status='DRY_RUN',
            image_path=None,
            prompt_path=str(saved['prompt_path']),
            metadata_path=str(saved['metadata_path']),
            final_prompt=payload.final_prompt,
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
            message='API 호출 없이 프롬프트만 생성했습니다.',
        )

    try:
        image_response = generate_image_base64(
            prompt=payload.final_prompt,
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
        )
        out = ensure_dir(output_dir)
        stamp = now_stamp()
        filename = f'cover_{safe_filename(payload.work_title)}_{payload.target_country}_{stamp}.{output_format}'
        image_path = save_base64_file(image_response.image_base64, Path(out) / filename)

        metadata = {
            **asdict(payload),
            'status': 'SUCCESS',
            'image_path': str(image_path),
            'model_name': model_name,
            'size': size,
            'quality': quality,
            'output_format': output_format,
        }
        save_json(metadata, saved['metadata_path'])

        return CoverGenerationResult(
            status='SUCCESS',
            image_path=str(image_path),
            prompt_path=str(saved['prompt_path']),
            metadata_path=str(saved['metadata_path']),
            final_prompt=payload.final_prompt,
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
            message='이미지 생성이 완료되었습니다.',
        )
    except OpenAIClientError as exc:
        return CoverGenerationResult(
            status='FAILED',
            image_path=None,
            prompt_path=str(saved['prompt_path']),
            metadata_path=str(saved['metadata_path']),
            final_prompt=payload.final_prompt,
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
            message=str(exc),
        )
    except Exception as exc:
        return CoverGenerationResult(
            status='FAILED',
            image_path=None,
            prompt_path=str(saved['prompt_path']),
            metadata_path=str(saved['metadata_path']),
            final_prompt=payload.final_prompt,
            model_name=model_name,
            size=size,
            quality=quality,
            output_format=output_format,
            message=f'이미지 생성 실패: {exc}',
        )

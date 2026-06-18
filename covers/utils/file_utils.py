import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def now_stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def hash_text(text):
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def ensure_dir(path):
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(text, fallback='cover'):
    raw = (text or '').strip().lower()
    raw = re.sub(r'\s+', '_', raw)
    raw = re.sub(r'[^0-9a-zA-Z가-힣_\-]', '', raw)
    raw = raw.strip('_')
    return raw[:80] or fallback


def save_json(data, path):
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return p


def save_text(text, path):
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(text, encoding='utf-8')
    return p


def save_base64_file(b64_text, path):
    p = Path(path)
    ensure_dir(p.parent)
    p.write_bytes(base64.b64decode(b64_text))
    return p

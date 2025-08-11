"""
유틸리티 함수 모듈
"""

import os
import uuid
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

# 환경 변수
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/home/catch/media"))
PUBLIC_BASE = os.getenv("PUBLIC_BASE_PATH", "/media")
DOMAIN_BASE_URL = os.getenv("DOMAIN_BASE_URL", "")

# 업로드 설정
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def make_job_id() -> str:
    """작업 ID 생성"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def to_public_url(abs_path: Path) -> str:
    """절대 경로를 공개 URL로 변환"""
    abs_str = str(abs_path)
    media_root_str = str(MEDIA_ROOT)
    assert abs_str.startswith(media_root_str), f"path not under MEDIA_ROOT: {abs_path}"
    rel = abs_str[len(media_root_str):]
    rel_url = f"{PUBLIC_BASE}{rel}"
    if DOMAIN_BASE_URL:
        return f"{DOMAIN_BASE_URL.rstrip('/')}{rel_url}"
    return rel_url


def is_allowed_file(filename: str, content_type: str = None) -> bool:
    """파일이 허용된 형식인지 확인"""
    if not filename:
        return False
    
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False
    
    if content_type and not content_type.startswith('image/'):
        return False
    
    return True


def generate_unique_filename(original_filename: str) -> str:
    """중복 방지를 위한 고유 파일명 생성 (원본 파일명 유지)"""
    file_path = Path(original_filename)
    name_without_ext = file_path.stem
    file_ext = file_path.suffix.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"{name_without_ext}_{timestamp}_{unique_id}{file_ext}"


def get_file_mime_type(filename: str) -> str:
    """파일의 MIME 타입 반환"""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def format_file_size(size_bytes: int) -> str:
    """파일 크기를 사람이 읽기 쉬운 형식으로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def progress_of_status(status: str) -> int:
    """상태에 따른 진행률 계산"""
    order = ["queued", "editing", "edited", "faceswap", "finalizing", "done", "failed"]
    try:
        return int(100 * order.index(status) / (len(order) - 1))
    except:
        return 0


def job_response_builder(job, job_dir_path: Path) -> dict:
    """작업 응답 생성 헬퍼"""
    input_png = job_dir_path/"input"/"input.png"
    edited_png = job_dir_path/"gpt"/"edited.png"
    final_png = job_dir_path/"final"/"result.png"
    
    artifacts = {
        "input": to_public_url(input_png) if input_png.exists() else None,
        "gpt": to_public_url(edited_png) if edited_png.exists() else None,
        "final": to_public_url(final_png) if final_png.exists() else None,
    }
    
    meta = {
        "params": to_public_url(job_dir_path/"params.json") if (job_dir_path/"params.json").exists() else None,
        "prompt": to_public_url(job_dir_path/"prompt.txt") if (job_dir_path/"prompt.txt").exists() else None,
        "logs": to_public_url(job_dir_path/"logs.txt") if (job_dir_path/"logs.txt").exists() else None,
    }
    
    return {
        "job_id": job.id,
        "status": job.status,
        "mode": getattr(job, 'mode', 'both'),
        "progress": progress_of_status(job.status),
        "artifacts": artifacts,
        "meta": meta,
        "error": job.error,
    }
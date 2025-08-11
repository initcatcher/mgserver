"""
작업 처리 서비스
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from sqlmodel import Session

from models import Job, JobEvent
from database import (
    get_session, now_utc, set_status, record_event,
    get_job, get_job_events, update_webhook_status
)
from utils import to_public_url
from pipelines import gpt_only_pipeline, face_only_pipeline, full_pipeline
from webhook import notify_job_success, notify_job_failure
from schemas import CreateImageJob, CreateGPTJob, CreateFaceJob, CreateJob
import os

logger = logging.getLogger(__name__)

# 환경 변수
MEDIA_ROOT = Path("/home/catch/media")
JOBS_DIR = MEDIA_ROOT / "jobs"
SIM_THRESHOLD = 0.35


def make_job_id() -> str:
    """작업 ID 생성"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def job_dir(job_id: str) -> Path:
    """작업 디렉토리 경로 반환"""
    return JOBS_DIR / job_id


def get_job_response(job: Job) -> dict:
    """작업 응답 생성"""
    base = job_dir(job.id)
    input_png = base / "input" / "input.png"
    edited_png = base / "gpt" / "edited.png"
    final_png = base / "final" / "result.png"

    artifacts = {
        "input": to_public_url(input_png) if input_png.exists() else None,
        "gpt": to_public_url(edited_png) if edited_png.exists() else None,
        "final": to_public_url(final_png) if final_png.exists() else None,
    }
    
    events = get_job_events(job.id)
    steps = [{"name": e.name, "at": e.at.isoformat()} for e in events]

    meta = {
        "params": to_public_url(base / "params.json") if (base / "params.json").exists() else None,
        "prompt": to_public_url(base / "prompt.txt") if (base / "prompt.txt").exists() else None,
        "logs": to_public_url(base / "logs.txt") if (base / "logs.txt").exists() else None,
    }

    return {
        "job_id": job.id,
        "status": job.status,
        "mode": job.mode,
        "progress": progress_of_status(job.status),
        "steps": steps,
        "artifacts": artifacts,
        "meta": meta,
        "error": job.error,
        "links": {
            "self": f"/jobs/{job.id}",
            "artifacts": f"/media/jobs/{job.id}/"
        }
    }


def progress_of_status(status: str) -> int:
    """상태별 진행률 계산"""
    order = ["queued", "editing", "edited", "faceswap", "finalizing", "done", "failed"]
    try:
        return int(100 * order.index(status) / (len(order) - 1))
    except:
        return 0


async def process_image_with_webhook(job_id: str, image_url: str, prompt: str,
                                    person_ids: list):
    """웹훅 알림이 포함된 이미지 처리"""
    try:
        # GPT 편집 실행 (얼굴 보존 마스크 사용)
        await gpt_only_pipeline(
            job_id,
            image_url,
            prompt,
            exif_strip=True,
            use_face_mask=True,  # 얼굴 보존
            mask_feather_pixels=15,
            face_expand_ratio=0.6,  # 머리카락까지 포함
            set_status_func=set_status,
            record_event_func=record_event
        )

        # 성공 시 웹훅 전송 (고정된 웹훅 URL 사용)
        base = job_dir(job_id)
        result_image = base / "final" / "result.png"
        if result_image.exists():
            processed_url = to_public_url(result_image)
            # TODO: 환경변수에서 고정 웹훅 URL 가져오기
            webhook_url = os.getenv("WEBHOOK_URL")
            if webhook_url:
                success = await notify_job_success(
                    job_id,
                    webhook_url,
                    image_url,
                    processed_url,
                    person_ids
                )
                update_webhook_status(job_id, "sent" if success else "failed")

    except Exception as e:
        logger.error(f"Image processing failed for {job_id}: {str(e)}")
        set_status(job_id, "failed", error=str(e))

        # 실패 시 웹훅 전송 (고정된 웹훅 URL 사용)
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            success = await notify_job_failure(
                job_id,
                webhook_url,
                error_code="PROCESSING_ERROR",
                error_message=str(e)
            )
            update_webhook_status(job_id, "sent" if success else "failed")


def create_image_job(payload: CreateImageJob) -> tuple[Job, str]:
    """새로운 형식의 이미지 작업 생성"""
    job_id = make_job_id()
    
    # 프롬프트 생성
    if payload.processing_options.type == "color":
        prompt = f"Change the background to {payload.processing_options.color} theme, preserve all people and faces"
    else:
        prompt = payload.processing_options.prompt

    job = Job(
        id=job_id,
        status="queued",
        mode="gpt_only",
        created_at=now_utc(),
        updated_at=now_utc(),
        input_image_url=payload.image_url,
        prompt=prompt,
        mapping="similarity",
        top1_only=False,
        threshold=SIM_THRESHOLD,
        person_ids=json.dumps(payload.person_ids),
        processing_type=payload.processing_options.type,
        processing_color=payload.processing_options.color,
        webhook_status="pending"
    )
    
    return job, prompt


def create_gpt_job(payload: CreateGPTJob) -> Job:
    """GPT 편집 작업 생성"""
    job_id = make_job_id()
    
    return Job(
        id=job_id,
        status="queued",
        mode="gpt_only",
        created_at=now_utc(),
        updated_at=now_utc(),
        input_image_url=payload.input_image_url,
        prompt=payload.prompt,
        mapping="similarity",
        top1_only=False,
        threshold=SIM_THRESHOLD
    )


def create_face_job(payload: CreateFaceJob) -> Job:
    """얼굴 교체 작업 생성"""
    job_id = make_job_id()
    mapping_str = payload.mapping if isinstance(payload.mapping, str) else json.dumps(payload.mapping)
    
    return Job(
        id=job_id,
        status="queued",
        mode="face_only",
        created_at=now_utc(),
        updated_at=now_utc(),
        input_image_url=payload.input_image_url,
        prompt="",  # Face-only는 프롬프트 불필요
        mapping=mapping_str,
        top1_only=payload.top1_only,
        threshold=payload.threshold
    )


def create_full_job(payload: CreateJob) -> Job:
    """전체 파이프라인 작업 생성"""
    job_id = make_job_id()
    mapping_str = payload.mapping if isinstance(payload.mapping, str) else json.dumps(payload.mapping)
    
    return Job(
        id=job_id,
        status="queued",
        mode="both",
        created_at=now_utc(),
        updated_at=now_utc(),
        input_image_url=payload.input_image_url,
        prompt=payload.prompt,
        mapping=mapping_str,
        top1_only=payload.top1_only,
        threshold=payload.threshold
    )
"""
작업 관련 API 엔드포인트
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse

from schemas import (
    CreateImageJob, ImageJobResponse, ErrorResponse,
    CreateGPTJob, CreateFaceJob, CreateJob,
    JobCreateResponse, JobResponse
)
from database import create_job as db_create_job, get_job as db_get_job, now_utc
from services.job_service import (
    create_image_job, create_gpt_job, create_face_job, create_full_job,
    get_job_response, process_image_with_webhook
)
from pipelines import gpt_only_pipeline, face_only_pipeline, full_pipeline
from background.task_runner import run_in_background
from database import set_status, record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=201,
         summary="이미지 처리 작업 (새로운 API)",
         description="Person ID 기반 이미지 처리 작업을 생성합니다.",
         response_model=ImageJobResponse,
         responses={
             400: {"model": ErrorResponse, "description": "Bad Request"},
             404: {"model": ErrorResponse, "description": "Not Found"}
         })
async def create_new_job(payload: CreateImageJob = Body(...)):
    """새로운 형식의 이미지 처리 작업"""
    logger.info(f"Creating image job with person_ids: {payload.person_ids}")
    
    # Validation
    if not payload.person_ids:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "person_ids must contain at least one valid person ID",
                    "details": {}
                }
            }
        )
    
    if payload.processing_options.type == "prompt" and not payload.processing_options.prompt:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "prompt is required when type is 'prompt'",
                    "details": {}
                }
            }
        )
    
    if payload.processing_options.type == "color" and not payload.processing_options.color:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "color is required when type is 'color'",
                    "details": {}
                }
            }
        )
    
    # 작업 생성
    job, prompt = create_image_job(payload)
    db_create_job(job)
    
    # 백그라운드에서 실행 (블로킹 없음!)
    run_in_background(
        process_image_with_webhook(
            job.id,
            payload.image_url,
            prompt,
            payload.person_ids
        )
    )
    
    # 즉시 응답
    return ImageJobResponse(
        data={
            "job_id": job.id,
            "status": "queued",
            "created_at": now_utc().isoformat()
        }
    )


@router.post("/gpt-edit", status_code=201,
         summary="GPT 이미지 편집 작업",
         description="OpenAI GPT를 사용한 이미지 편집만 수행합니다.",
         response_model=JobCreateResponse)
async def create_gpt_only_job(payload: CreateGPTJob = Body(...)):
    """GPT 편집 전용 엔드포인트"""
    job = create_gpt_job(payload)
    db_create_job(job)
    
    # 마스크 파라미터 처리
    use_face_mask = getattr(payload, 'use_face_mask', False)
    mask_feather_pixels = getattr(payload, 'mask_feather_pixels', 12)
    face_expand_ratio = getattr(payload, 'face_expand_ratio', 0.3)
    
    # 백그라운드에서 실행
    run_in_background(
        gpt_only_pipeline(
            job.id,
            payload.input_image_url,
            payload.prompt,
            payload.exif_strip,
            use_face_mask,
            mask_feather_pixels,
            face_expand_ratio,
            set_status,
            record_event
        )
    )
    
    return JobCreateResponse(
        job_id=job.id,
        mode="gpt_only",
        status="queued",
        message="GPT image editing job created successfully",
        links={
            "self": f"/jobs/{job.id}",
            "artifacts": f"/media/jobs/{job.id}/"
        }
    )


@router.post("/face-swap", status_code=201,
         summary="얼굴 교체 작업",
         description="FaceFusion을 사용한 얼굴 교체만 수행합니다.",
         response_model=JobCreateResponse)
async def create_face_only_job(payload: CreateFaceJob = Body(...)):
    """FaceFusion 얼굴 교체 전용 엔드포인트"""
    job = create_face_job(payload)
    db_create_job(job)
    
    # 백그라운드에서 실행
    run_in_background(
        face_only_pipeline(
            job.id,
            payload.input_image_url,
            payload.faces,
            payload.mapping,
            payload.top1_only,
            payload.threshold,
            payload.exif_strip,
            set_status,
            record_event
        )
    )
    
    return JobCreateResponse(
        job_id=job.id,
        mode="face_only",
        status="queued",
        message="Face swap job created successfully",
        links={
            "self": f"/jobs/{job.id}",
            "artifacts": f"/media/jobs/{job.id}/"
        }
    )


@router.post("/legacy", status_code=201,
         summary="통합 작업 생성 (GPT + FaceFusion)",
         description="AI 이미지 편집과 얼굴 교체를 모두 수행합니다.",
         response_model=JobCreateResponse)
async def create_legacy_job(payload: CreateJob = Body(...)):
    """통합 작업 생성 - GPT 편집과 FaceFusion을 모두 수행"""
    job = create_full_job(payload)
    db_create_job(job)
    
    # 백그라운드에서 실행
    run_in_background(
        full_pipeline(job.id, payload, set_status, record_event)
    )
    
    return JobCreateResponse(
        job_id=job.id,
        mode="both",
        status="queued",
        message="Full pipeline job created successfully (GPT + FaceFusion)",
        links={
            "self": f"/jobs/{job.id}",
            "artifacts": f"/media/jobs/{job.id}/"
        }
    )


@router.get("/{job_id}",
         summary="작업 상태 조회",
         description="작업 ID로 진행상황과 결과를 조회합니다.",
         response_model=JobResponse)
def get_job_status(job_id: str):
    """작업 상태 조회"""
    job = db_get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return get_job_response(job)
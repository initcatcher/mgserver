"""
Job API endpoints
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse

from schemas import (
    CreateImageJob, ImageJobResponse, ErrorResponse,
    CreateGPTJob, CreateFaceJob, CreateJob,
    JobCreateResponse, JobResponse
)
from services.job_manager import job_manager, JobStatus
from services.image_service import image_service
from services.face_queue import face_queue
from utils import to_public_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=201,
         summary="Image processing job (new API)",
         description="Create image processing job based on Person IDs",
         response_model=ImageJobResponse,
         responses={
             400: {"model": ErrorResponse, "description": "Bad Request"},
             404: {"model": ErrorResponse, "description": "Not Found"}
         })
async def create_new_job(payload: CreateImageJob = Body(...)):
    """New format image processing job"""
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
    
    # Create job
    job_id = job_manager.create_job("full")
    
    # Start processing
    asyncio.create_task(
        image_service.process_full_workflow(
            job_id,
            payload.image_url,
            payload.person_ids,
            payload.processing_options.dict()
        )
    )
    
    # Return immediate response
    return ImageJobResponse(
        data={
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat()
        }
    )


@router.post("/gpt-edit", status_code=201,
         summary="GPT image editing job",
         description="Image editing using OpenAI GPT only",
         response_model=JobCreateResponse)
async def create_gpt_only_job(payload: CreateGPTJob = Body(...)):
    """GPT editing only endpoint"""
    job_id = job_manager.create_job("gpt_only")
    
    # Start GPT processing
    asyncio.create_task(
        image_service.process_gpt_only(
            job_id,
            payload.input_image_url,
            payload.prompt
        )
    )
    
    return JobCreateResponse(
        job_id=job_id,
        mode="gpt_only",
        status="queued",
        message="GPT image editing job created successfully",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@router.post("/face-swap", status_code=201,
         summary="Face swap job",
         description="Face swap using FaceFusion only",
         response_model=JobCreateResponse)
async def create_face_only_job(payload: CreateFaceJob = Body(...)):
    """FaceFusion face swap only endpoint"""
    job_id = job_manager.create_job("face_only")
    
    # Prepare face URLs
    face_urls = []
    for face_ref in payload.faces:
        if hasattr(face_ref, 'url'):
            face_urls.append(face_ref.url)
        elif isinstance(face_ref, str):
            face_urls.append(face_ref)
    
    # Start face processing
    asyncio.create_task(
        image_service.process_face_only(
            job_id,
            payload.input_image_url,
            face_urls
        )
    )
    
    return JobCreateResponse(
        job_id=job_id,
        mode="face_only",
        status="queued",
        message="Face swap job created successfully",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@router.post("/legacy", status_code=201,
         summary="Integrated job creation (GPT + FaceFusion)",
         description="Perform both AI image editing and face swap",
         response_model=JobCreateResponse)
async def create_legacy_job(payload: CreateJob = Body(...)):
    """Integrated job - both GPT editing and FaceFusion"""
    job_id = job_manager.create_job("both")
    
    # Convert face references to URLs
    person_ids = []
    for face in payload.faces:
        if hasattr(face, 'url'):
            person_ids.append(face.url)
        elif isinstance(face, str):
            person_ids.append(face)
    
    # Build processing options
    processing_options = {
        "type": "prompt",
        "prompt": payload.prompt
    }
    
    # Start full workflow
    asyncio.create_task(
        image_service.process_full_workflow(
            job_id,
            payload.input_image_url,
            person_ids,
            processing_options
        )
    )
    
    return JobCreateResponse(
        job_id=job_id,
        mode="both",
        status="queued",
        message="Full pipeline job created successfully (GPT + FaceFusion)",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@router.get("/{job_id}",
         summary="Get job status",
         description="Query job progress and results by job ID",
         response_model=JobResponse)
def get_job_status(job_id: str):
    """Get job status"""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    
    # Build response
    job_dir = Path("/home/catch/media/jobs") / job_id
    
    # Check for result files
    artifacts = {}
    if job_dir.exists():
        gpt_result = job_dir / "gpt_result.jpg"
        final_result = job_dir / "final_result.jpg"
        
        if final_result.exists():
            artifacts["final"] = to_public_url(final_result)
        elif gpt_result.exists():
            artifacts["final"] = to_public_url(gpt_result)
        
        if gpt_result.exists():
            artifacts["gpt"] = to_public_url(gpt_result)
    
    return JobResponse(
        job_id=job_id,
        status=job["status"],
        mode=job.get("type", "both"),
        progress=job.get("progress", 0),
        steps=[],  # Simplified - no detailed steps
        artifacts=artifacts,
        meta={},
        error=job.get("error"),
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@router.get("/queue/status",
         summary="Get queue status",
         description="Get current queue statistics")
def get_queue_status():
    """Get queue status"""
    return {
        "jobs": job_manager.get_queue_status(),
        "face_queue": {
            "size": face_queue.get_queue_size(),
            "current": face_queue.get_current_task()
        }
    }
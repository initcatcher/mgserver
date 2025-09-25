"""
Frame API endpoints
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from schemas import CreateFrameJob, FrameJobResponse
from services.job_manager import job_manager
from services.webhook_service import webhook_service
from services.frame_processor import frame_processor
from utils import convert_url_to_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frame", tags=["frame"])


async def handle_frame_job(job_id: str, image_urls: list, frame_color: str) -> None:
    """Handle actual frame job: process images and create frame"""
    try:
        logger.info(f"Starting frame job {job_id}")
        logger.info(f"Frame job details - URLs: {image_urls}, Color: {frame_color}")
        
        # Validate input
        if not image_urls or len(image_urls) > 4:
            raise ValueError(f"Invalid number of images: {len(image_urls)}. Expected 1-4 images.")
        
        # Convert URLs to local paths
        image_paths = []
        for url in image_urls:
            local_path = convert_url_to_path(url)
            if not Path(local_path).exists():
                raise FileNotFoundError(f"Image not found: {local_path}")
            image_paths.append(local_path)
        
        logger.info(f"Processing {len(image_paths)} images with color {frame_color}")
        
        # Process frame using frame_processor
        frame_processor.process_frame_job(
            job_id=job_id,
            image_paths=image_paths,
            frame_color=frame_color
        )
        
        # Update job status to done
        job_manager.update_job_status(job_id, "done")
        job_manager.update_job_progress(job_id, 100)
        
        # Get webhook params
        webhook_params = job_manager.get_webhook_params(job_id)
        
        # Prepare webhook data
        original_image_id = webhook_params.get("original_image_id", "frame_job")
        processed_image_url = f"https://image.nearzoom.store/media/jobs/{job_id}/frame_result.jpg"
        person_ids = webhook_params.get("person_ids", [])
        
        logger.info(f"Frame job {job_id} completed - Sending webhook to: https://api.nearzoom.store/webhooks/frame/completed")
        logger.info(f"Webhook payload - originalImageId: {original_image_id}, processedImageUrl: {processed_image_url}, personIds: {person_ids}")
        
        # Send frame completion webhook
        webhook_sent = await webhook_service.send_frame_completion_webhook(
            job_id=job_id,
            original_image_id=original_image_id,
            finalImageUrl=processed_image_url,
            person_ids=person_ids
        )
        
        if webhook_sent:
            logger.info(f"✅ Frame webhook sent successfully for job {job_id}")
        else:
            logger.error(f"❌ Failed to send frame webhook for job {job_id}")
        
        logger.info(f"Frame job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Frame job {job_id} failed: {str(e)}")
        job_manager.update_job_status(job_id, "failed")
        job_manager.update_job_error(job_id, f"Frame job failed: {str(e)}")


@router.post("", status_code=201,
         summary="Frame processing job",
         description="Create frame processing job for multiple images",
         response_model=FrameJobResponse)
async def create_frame_job(payload: CreateFrameJob = Body(...)):
    """Create frame processing job"""
    logger.info(f"Creating frame job with {len(payload.image_urls)} images, color: {payload.frameColor}")
    
    # Validation
    if not payload.image_urls:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "image_urls must contain at least one URL",
                    "details": {}
                }
            }
        )
    
    # Create job
    job_id = job_manager.create_job("frame")
    
    # Extract IDs from image URLs for webhook
    person_ids = []
    original_image_id = "frame_" + job_id  # Use frame prefix with job ID
    
    for url in payload.image_urls:
        # Extract ID from URL (e.g., job_1691745000123_result.jpg -> job_1691745000123)
        filename = url.split("/")[-1]
        # Remove extension and _result suffix if present
        file_id = filename.replace(".jpg", "").replace("_result", "")
        person_ids.append(file_id)
    
    # Set webhook parameters
    webhook_params = {
        "original_image_id": original_image_id,
        "person_ids": person_ids
    }
    job_manager.set_webhook_params(job_id, webhook_params)
    
    # Start actual frame processing
    asyncio.create_task(handle_frame_job(job_id, payload.image_urls, payload.frameColor))
    
    # Return immediate response
    return FrameJobResponse(
        data={
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat()
        }
    )
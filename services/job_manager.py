"""
Memory-based job state management
"""

import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum

class JobStatus(Enum):
    QUEUED = "queued"
    GPT_PROCESSING = "gpt_processing" 
    FACE_PROCESSING = "face_processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, dict] = {}
        # Lazy import to avoid circular imports
        self._webhook_service = None
    
    def create_job(self, job_type: str = "full") -> str:
        """Create new job and return job_id"""
        job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        
        self.jobs[job_id] = {
            "id": job_id,
            "type": job_type,  # "gpt_only", "face_only", "full"
            "status": JobStatus.QUEUED.value,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "result_path": None,
            "error": None,
            "logs": [],
            "progress": 0,
            "webhook_params": {}  # Store webhook-related data
        }
        return job_id
    
    def update_status(self, job_id: str, status: JobStatus, error: str = None):
        """Update job status"""
        if job_id in self.jobs:
            old_status = self.jobs[job_id]["status"]
            self.jobs[job_id]["status"] = status.value
            self.jobs[job_id]["updated_at"] = datetime.now()
            if error:
                self.jobs[job_id]["error"] = error
            
            # Update progress based on status
            progress_map = {
                JobStatus.QUEUED: 0,
                JobStatus.GPT_PROCESSING: 30,
                JobStatus.FACE_PROCESSING: 60,
                JobStatus.COMPLETED: 100,
                JobStatus.FAILED: -1
            }
            self.jobs[job_id]["progress"] = progress_map.get(status, 0)
            
            # Send webhook for completion or failure
            if status in [JobStatus.COMPLETED, JobStatus.FAILED] and old_status != status.value:
                asyncio.create_task(self._send_webhook(job_id, status, error))
    
    def add_log(self, job_id: str, message: str):
        """Add log entry for job"""
        if job_id in self.jobs:
            self.jobs[job_id]["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "message": message
            })
    
    def set_result(self, job_id: str, result_path: str):
        """Set result path for completed job"""
        if job_id in self.jobs:
            self.jobs[job_id]["result_path"] = result_path
            self.jobs[job_id]["updated_at"] = datetime.now()
    
    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    def get_all_jobs(self) -> List[dict]:
        """Get all jobs"""
        return list(self.jobs.values())
    
    def get_queue_status(self) -> dict:
        """Get queue statistics"""
        statuses = [job["status"] for job in self.jobs.values()]
        return {
            "total": len(self.jobs),
            "queued": statuses.count(JobStatus.QUEUED.value),
            "gpt_processing": statuses.count(JobStatus.GPT_PROCESSING.value),
            "face_processing": statuses.count(JobStatus.FACE_PROCESSING.value),
            "completed": statuses.count(JobStatus.COMPLETED.value),
            "failed": statuses.count(JobStatus.FAILED.value)
        }
    
    def cleanup_old_jobs(self, hours: int = 24):
        """Remove jobs older than specified hours"""
        cutoff = datetime.now().timestamp() - (hours * 3600)
        to_remove = [
            job_id for job_id, job in self.jobs.items()
            if job["created_at"].timestamp() < cutoff
        ]
        for job_id in to_remove:
            del self.jobs[job_id]
        return len(to_remove)
    
    def set_webhook_params(self, job_id: str, params: dict):
        """Set webhook parameters for job"""
        if job_id in self.jobs:
            self.jobs[job_id]["webhook_params"] = params
    
    def update_job_status(self, job_id: str, status: str):
        """Update job status (string version for backward compatibility)"""
        status_map = {
            "done": JobStatus.COMPLETED,
            "failed": JobStatus.FAILED,
            "queued": JobStatus.QUEUED
        }
        if status in status_map:
            self.update_status(job_id, status_map[status])
    
    def update_job_progress(self, job_id: str, progress: int):
        """Update job progress"""
        if job_id in self.jobs:
            self.jobs[job_id]["progress"] = progress
            self.jobs[job_id]["updated_at"] = datetime.now()
    
    def update_job_error(self, job_id: str, error: str):
        """Update job error"""
        if job_id in self.jobs:
            self.jobs[job_id]["error"] = error
            self.jobs[job_id]["updated_at"] = datetime.now()
    
    async def _send_webhook(self, job_id: str, status: JobStatus, error: str = None):
        """Send webhook notification"""
        try:
            # Lazy import to avoid circular imports
            if self._webhook_service is None:
                from services.webhook_service import webhook_service
                self._webhook_service = webhook_service
            
            job = self.jobs.get(job_id)
            if not job:
                return
            
            webhook_params = job.get("webhook_params", {})
            
            if status == JobStatus.COMPLETED:
                # Extract data for success webhook
                result_path = job.get("result_path")
                if result_path:
                    # Convert local path to public URL
                    processed_url = result_path.replace("/home/catch/media", "https://image.nearzoom.store/media")
                else:
                    # Fallback URL for dummy jobs
                    processed_url = f"https://image.nearzoom.store/media/jobs/{job_id}/final_result.jpg"
                
                original_image_id = webhook_params.get("original_image_id", "unknown")
                person_ids = webhook_params.get("person_ids", [])
                
                await self._webhook_service.send_completion_webhook(
                    job_id=job_id,
                    original_image_id=original_image_id,
                    processed_image_url=processed_url,
                    person_ids=person_ids
                )
            
            elif status == JobStatus.FAILED:
                original_image_id = webhook_params.get("original_image_id", "unknown")
                error_message = error or job.get("error", "Unknown error")
                
                await self._webhook_service.send_failure_webhook(
                    job_id=job_id,
                    error_message=error_message,
                    original_image_id=original_image_id
                )
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Webhook sending failed for job {job_id}: {str(e)}")

# Singleton instance
job_manager = JobManager()
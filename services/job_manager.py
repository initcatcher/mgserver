"""
Memory-based job state management
"""

import uuid
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
            "progress": 0
        }
        return job_id
    
    def update_status(self, job_id: str, status: JobStatus, error: str = None):
        """Update job status"""
        if job_id in self.jobs:
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

# Singleton instance
job_manager = JobManager()
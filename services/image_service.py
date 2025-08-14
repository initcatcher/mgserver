"""
Integrated image processing service
Combines GPT generation and FaceFusion workflows
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

from services.job_manager import job_manager, JobStatus
from services.gpt_processor import gpt_processor
from services.face_queue import face_queue
from utils import convert_url_to_path, to_public_url

logger = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        self.media_root = Path("/home/catch/media")
        self.jobs_dir = self.media_root / "jobs"
    
    async def process_full_workflow(self, 
                                   job_id: str,
                                   image_url: str,
                                   person_ids: List[str],
                                   processing_options: dict):
        """Full workflow: GPT generation + Face swap"""
        try:
            # Setup job directory
            job_dir = self.jobs_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            
            # Write job parameters
            self._save_job_params(job_dir, {
                "image_url": image_url,
                "person_ids": person_ids,
                "processing_options": processing_options
            })
            
            # Update status to GPT processing
            job_manager.update_status(job_id, JobStatus.GPT_PROCESSING)
            job_manager.add_log(job_id, "Starting GPT image generation")
            
            # Convert URL to local path
            base_image_path = convert_url_to_path(image_url)
            if not Path(base_image_path).exists():
                raise FileNotFoundError(f"Base image not found: {base_image_path}")
            
            # Generate GPT image
            gpt_output_path = str(job_dir / "gpt_result.jpg")
            prompt = self._build_prompt(processing_options)
            
            success, result = await gpt_processor.process_image(
                base_image_path,
                gpt_output_path,
                prompt
            )
            
            if not success:
                raise Exception(f"GPT generation failed: {result}")
            
            job_manager.add_log(job_id, f"GPT generation completed: {gpt_output_path}")
            
            # Convert person URLs to paths and preserve original indices
            person_paths = []
            for i, person_url in enumerate(person_ids):
                if not person_url or person_url.strip() == "":
                    logger.warning(f"Skipping empty person_id at position {i}")
                    continue
                    
                person_path = convert_url_to_path(person_url)
                if not Path(person_path).exists():
                    logger.warning(f"Person image not found: {person_path}")
                    continue
                person_paths.append((i, person_path))
            
            if person_paths:
                # Update status to face processing
                job_manager.update_status(job_id, JobStatus.FACE_PROCESSING)
                job_manager.add_log(job_id, f"Starting face swap for {len(person_paths)} faces")
                
                # Add to face queue
                face_job = {
                    'job_id': job_id,
                    'target_image': gpt_output_path,
                    'source_faces': person_paths,
                    'output_dir': str(job_dir),
                    'callback': lambda success, result: self._face_callback(job_id, success, result)
                }
                
                await face_queue.add_job(face_job)
            else:
                # No faces to swap, mark as completed
                job_manager.set_result(job_id, gpt_output_path)
                job_manager.update_status(job_id, JobStatus.COMPLETED)
                job_manager.add_log(job_id, "Completed (no face swap needed)")
            
        except Exception as e:
            logger.error(f"Workflow error for job {job_id}: {str(e)}")
            job_manager.update_status(job_id, JobStatus.FAILED, str(e))
            job_manager.add_log(job_id, f"Error: {str(e)}")
    
    async def process_gpt_only(self,
                              job_id: str,
                              image_url: str,
                              prompt: str):
        """GPT-only processing"""
        try:
            job_dir = self.jobs_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            
            job_manager.update_status(job_id, JobStatus.GPT_PROCESSING)
            
            base_image_path = convert_url_to_path(image_url)
            output_path = str(job_dir / "gpt_result.jpg")
            
            success, result = await gpt_processor.process_image(
                base_image_path,
                output_path,
                prompt
            )
            
            if success:
                job_manager.set_result(job_id, result)
                job_manager.update_status(job_id, JobStatus.COMPLETED)
            else:
                job_manager.update_status(job_id, JobStatus.FAILED, result)
                
        except Exception as e:
            logger.error(f"GPT processing error: {str(e)}")
            job_manager.update_status(job_id, JobStatus.FAILED, str(e))
    
    async def process_face_only(self,
                               job_id: str,
                               target_url: str,
                               person_ids: List[str]):
        """Face-only processing"""
        try:
            job_dir = self.jobs_dir / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            
            job_manager.update_status(job_id, JobStatus.FACE_PROCESSING)
            
            target_path = convert_url_to_path(target_url)
            
            # Convert person URLs to paths and preserve original indices
            source_paths = []
            for i, person_url in enumerate(person_ids):
                if not person_url or person_url.strip() == "":
                    logger.warning(f"Skipping empty person_id at position {i}")
                    continue
                    
                person_path = convert_url_to_path(person_url)
                if not Path(person_path).exists():
                    logger.warning(f"Person image not found: {person_path}")
                    continue
                source_paths.append((i, person_path))
            
            if not source_paths:
                # No valid faces to swap, mark as completed with original image
                job_manager.set_result(job_id, target_path)
                job_manager.update_status(job_id, JobStatus.COMPLETED)
                job_manager.add_log(job_id, "Completed (no valid faces to swap)")
                return
            
            face_job = {
                'job_id': job_id,
                'target_image': target_path,
                'source_faces': source_paths,
                'output_dir': str(job_dir),
                'callback': lambda success, result: self._face_callback(job_id, success, result)
            }
            
            await face_queue.add_job(face_job)
            
        except Exception as e:
            logger.error(f"Face processing error: {str(e)}")
            job_manager.update_status(job_id, JobStatus.FAILED, str(e))
    
    async def _face_callback(self, job_id: str, success: bool, result: str):
        """Callback for face queue completion"""
        if success:
            job_manager.set_result(job_id, result)
            job_manager.update_status(job_id, JobStatus.COMPLETED)
            job_manager.add_log(job_id, f"Face swap completed: {result}")
        else:
            job_manager.update_status(job_id, JobStatus.FAILED, result)
            job_manager.add_log(job_id, f"Face swap failed: {result}")
    
    def _build_prompt(self, processing_options: dict) -> str:
        """Build prompt from processing options"""
        processing_type = processing_options.get("type", "prompt")
        
        if processing_type == "color":
            color = processing_options.get("color", "#FFFFFF")
            return f"Transform into a group photo with {color} background color"
        else:
            return processing_options.get("prompt", "Create a group photo")
    
    def _save_job_params(self, job_dir: Path, params: dict):
        """Save job parameters to file"""
        params_file = job_dir / "params.json"
        with open(params_file, 'w') as f:
            json.dump(params, f, indent=2)
    
    def _save_logs(self, job_id: str):
        """Save job logs to file"""
        job = job_manager.get_job(job_id)
        if job and job.get('logs'):
            job_dir = self.jobs_dir / job_id
            log_file = job_dir / "process.log"
            with open(log_file, 'w') as f:
                for log_entry in job['logs']:
                    f.write(f"[{log_entry['timestamp']}] {log_entry['message']}\n")

# Singleton instance
image_service = ImageService()
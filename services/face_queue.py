"""
FaceFusion single queue worker - ensures only one face swap runs at a time
"""

import asyncio
import logging
from pathlib import Path
from typing import Tuple, List, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class FaceFusionQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.current_task = None
        self.worker_task = None
        self.is_running = False
    
    async def start(self):
        """Start the queue worker"""
        if not self.is_running:
            self.is_running = True
            self.worker_task = asyncio.create_task(self._worker())
            logger.info("FaceFusion queue worker started")
    
    async def stop(self):
        """Stop the queue worker"""
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("FaceFusion queue worker stopped")
    
    async def add_job(self, job_data: dict):
        """Add a job to the queue"""
        await self.queue.put(job_data)
        logger.info(f"Job {job_data.get('job_id')} added to FaceFusion queue. Queue size: {self.queue.qsize()}")
    
    async def _worker(self):
        """Worker that processes jobs from the queue one at a time"""
        while self.is_running:
            try:
                # Wait for a job with timeout to allow checking is_running
                job_data = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                self.current_task = job_data.get('job_id')
                
                logger.info(f"Processing FaceFusion job: {self.current_task}")
                
                # Process the face swap
                success, result = await self._process_face_swap(job_data)
                
                # Update job status through callback
                if job_data.get('callback'):
                    await job_data['callback'](success, result)
                
                self.current_task = None
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in FaceFusion worker: {str(e)}")
                self.current_task = None
    
    async def _process_face_swap(self, job_data: dict) -> Tuple[bool, str]:
        """Process face swap with sequential execution for multiple faces"""
        try:
            target_image = job_data.get('target_image')
            source_faces = job_data.get('source_faces', [])
            output_dir = job_data.get('output_dir')
            job_id = job_data.get('job_id')
            
            if not source_faces:
                return True, target_image  # No faces to swap, return original
            
            # Ensure output directory exists
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            current_target = target_image
            
            # Process each face sequentially
            for i, source_face in enumerate(source_faces):
                logger.info(f"Job {job_id}: Processing face {i+1}/{len(source_faces)}")
                
                # Determine output path
                if i == len(source_faces) - 1:
                    # Final output
                    output_path = str(Path(output_dir) / "final_result.jpg")
                else:
                    # Intermediate step
                    output_path = str(Path(output_dir) / f"temp_step_{i+1}.jpg")
                
                # Run FaceFusion for this face
                success, result = await self._run_single_face_swap(
                    source_face, current_target, output_path, i
                )
                
                if not success:
                    return False, f"Face swap failed at step {i+1}: {result}"
                
                current_target = result
            
            logger.info(f"Job {job_id}: All face swaps completed successfully")
            return True, current_target
            
        except Exception as e:
            logger.error(f"Face swap processing error: {str(e)}")
            return False, str(e)
    
    async def _run_single_face_swap(self, source_path: str, target_path: str, 
                                   output_path: str, face_position: int) -> Tuple[bool, str]:
        """Run a single face swap operation"""
        try:
            # Validate paths
            source = Path(source_path)
            target = Path(target_path)
            output = Path(output_path)
            
            if not source.exists():
                return False, f"Source file not found: {source_path}"
            if not target.exists():
                return False, f"Target file not found: {target_path}"
            
            # Create output directory
            output.parent.mkdir(parents=True, exist_ok=True)
            
            # FaceFusion command
            cmd = [
                '/home/catch/miniconda3/envs/facefusion/bin/python',
                '/home/catch/facefusion/facefusion.py',
                'headless-run',
                '-s', str(source.resolve()),
                '-t', str(target.resolve()),
                '-o', str(output.resolve()),
                '--face-swapper-model', 'inswapper_128_fp16',
                '--face-selector-order', 'left-right',
                '--reference-face-position', str(face_position)
            ]
            
            logger.info(f"Executing FaceFusion: position={face_position}")
            
            # Execute async subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd='/home/catch/facefusion'
            )
            
            # Wait for completion
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and output.exists():
                logger.info(f"Face swap successful: {output}")
                return True, str(output)
            else:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                logger.error(f"Face swap failed: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            logger.error(f"Face swap error: {str(e)}")
            return False, str(e)
    
    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()
    
    def get_current_task(self) -> Optional[str]:
        """Get currently processing task ID"""
        return self.current_task

# Singleton instance
face_queue = FaceFusionQueue()
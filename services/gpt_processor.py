"""
GPT parallel processing pool
"""

import asyncio
import base64
import os
import logging
from pathlib import Path
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class GPTProcessor:
    def __init__(self, max_workers: int = 4):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks = []
        logger.info(f"GPT processor initialized with {max_workers} workers")
    
    async def process_image(self, 
                           base_image_path: str,
                           output_path: str,
                           prompt: str,
                           mask_path: Optional[str] = None) -> Tuple[bool, str]:
        """Process image with GPT (async wrapper for parallel execution)"""
        try:
            # Run GPT processing in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._generate_image_sync,
                base_image_path,
                output_path,
                prompt,
                mask_path
            )
            return result
        except Exception as e:
            logger.error(f"GPT processing error: {str(e)}")
            return False, str(e)
    
    def _generate_image_sync(self,
                            base_image_path: str,
                            output_path: str,
                            prompt: str,
                            mask_path: Optional[str] = None) -> Tuple[bool, str]:
        """Synchronous GPT image generation"""
        try:
            # Add preservation instruction to prompt
            enhanced_prompt = prompt + " Preserve the original pixels of the subjects face, skin, eyes, hair, contours, and expression exactly as they are — no retouching. Naturally generate the clothing and body, filling in any missing parts."
            
            # Prepare API call parameters
            kwargs = dict(
                model="gpt-image-1",
                prompt=enhanced_prompt,
                size="1024x1024",
                input_fidelity="high",
            )
            
            # Call OpenAI API
            if mask_path and Path(mask_path).exists():
                with open(base_image_path, "rb") as img, open(mask_path, "rb") as msk:
                    result = self.client.images.edit(image=img, mask=msk, **kwargs)
            else:
                with open(base_image_path, "rb") as img:
                    result = self.client.images.edit(image=img, **kwargs)
            
            # Save result
            b64_data = result.data[0].b64_json
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(b64_data))
            
            logger.info(f"GPT image generated: {output_path}")
            return True, output_path
            
        except Exception as e:
            logger.error(f"GPT generation failed: {str(e)}")
            return False, str(e)
    
    async def process_batch(self, jobs: list) -> list:
        """Process multiple GPT jobs in parallel"""
        tasks = []
        for job in jobs:
            task = self.process_image(
                job['base_image'],
                job['output_path'],
                job['prompt'],
                job.get('mask_path')
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=True)
        logger.info("GPT processor shutdown")

# Singleton instance
gpt_processor = GPTProcessor(max_workers=int(os.getenv("GPT_MAX_WORKERS", "4")))
"""
Webhook service for job completion notifications
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
import httpx
import os

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self):
        self.webhook_url = os.getenv(
            "WEBHOOK_URL", 
            "https://api.nearzoom.store/webhooks/image/individual/completed"
        )
        self.timeout = 10.0
        self.retry_count = 1
    
    async def send_completion_webhook(self, 
                                    job_id: str,
                                    original_image_id: str,
                                    processed_image_url: str,
                                    person_ids: List[str]) -> bool:
        """Send webhook for successful job completion"""
        payload = {
            "event": "image_processing_completed",
            "jobId": job_id,
            "timestamp": datetime.now().isoformat() + "Z",
            "data": {
                "originalImageId": original_image_id,
                "processedImageUrl": processed_image_url,
                "personIds": person_ids
            }
        }
        
        return await self._send_webhook(payload)
    
    async def send_failure_webhook(self,
                                 job_id: str,
                                 error_message: str,
                                 original_image_id: str = None) -> bool:
        """Send webhook for job failure"""
        payload = {
            "event": "image_processing_failed",
            "jobId": job_id,
            "timestamp": datetime.now().isoformat() + "Z",
            "data": {
                "error": error_message,
                "originalImageId": original_image_id or "unknown"
            }
        }
        
        return await self._send_webhook(payload)
    
    async def _send_webhook(self, payload: Dict) -> bool:
        """Internal method to send webhook with retry logic"""
        for attempt in range(self.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        try:
                            response_data = response.json()
                            message = response_data.get("message", "Webhook sent successfully")
                            logger.info(f"Webhook sent successfully for job {payload['jobId']}: {message}")
                            return True
                        except Exception:
                            logger.info(f"Webhook sent successfully for job {payload['jobId']} (no JSON response)")
                            return True
                    else:
                        logger.warning(f"Webhook failed with status {response.status_code} for job {payload['jobId']}")
                        
            except httpx.TimeoutException:
                logger.warning(f"Webhook timeout (attempt {attempt + 1}) for job {payload['jobId']}")
            except Exception as e:
                logger.error(f"Webhook error (attempt {attempt + 1}) for job {payload['jobId']}: {str(e)}")
            
            # Wait before retry
            if attempt < self.retry_count:
                await asyncio.sleep(2)
        
        logger.error(f"Webhook failed after {self.retry_count + 1} attempts for job {payload['jobId']}")
        return False

# Singleton instance
webhook_service = WebhookService()
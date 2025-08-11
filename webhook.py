"""
웹훅 처리 모듈
작업 완료/실패 시 웹훅 전송
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

# 웹훅 시크릿 (환경변수로 관리 권장)
WEBHOOK_SECRET = "your-webhook-secret-key"  # TODO: .env에서 로드


class WebhookSender:
    """웹훅 전송 클래스"""
    
    def __init__(self, secret: str = WEBHOOK_SECRET):
        self.secret = secret
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self.max_retries = 3
        self.retry_delay = 5  # seconds
    
    def generate_signature(self, payload: str) -> str:
        """웹훅 서명 생성 (HMAC-SHA256)"""
        signature = hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    async def send_webhook(self, url: str, event_type: str, data: Dict[str, Any]) -> bool:
        """웹훅 전송 (재시도 포함)"""
        if not url:
            logger.warning("No webhook URL provided")
            return False
        
        payload = json.dumps(data, ensure_ascii=False)
        signature = self.generate_signature(payload)
        
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event_type,
            "X-Webhook-Signature": signature
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url,
                        content=payload,
                        headers=headers
                    )
                    
                    if response.status_code in [200, 201, 202, 204]:
                        logger.info(f"Webhook sent successfully to {url} (attempt {attempt + 1})")
                        return True
                    else:
                        logger.warning(
                            f"Webhook failed with status {response.status_code} "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )
                        
            except Exception as e:
                logger.error(
                    f"Webhook sending error (attempt {attempt + 1}/{self.max_retries}): {str(e)}"
                )
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay)
        
        logger.error(f"Failed to send webhook after {self.max_retries} attempts")
        return False
    
    async def send_success_webhook(self, 
                                  webhook_url: str,
                                  job_id: str,
                                  original_image_url: str,
                                  processed_image_url: str,
                                  person_ids: list) -> bool:
        """성공 웹훅 전송"""
        # 웹훅 스펙에 맞는 payload 구조
        data = {
            "event": "image-processing.completed",
            "jobId": job_id,  # camelCase로 변경
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "originalImageId": original_image_url,  # camelCase로 변경
                "processedImageUrl": processed_image_url,  # camelCase로 변경
                "personIds": person_ids  # camelCase로 변경
            }
        }
        
        # 성공 웹훅 전용 엔드포인트 사용
        success_url = f"{webhook_url.rstrip('/')}/webhooks/image-processing/completed"
        
        return await self.send_webhook(
            success_url,
            "image-processing.completed",
            data
        )
    
    async def send_failure_webhook(self,
                                  webhook_url: str,
                                  job_id: str,
                                  error_code: str,
                                  error_message: str) -> bool:
        """실패 웹훅 전송"""
        # 웹훅 스펙에 맞는 payload 구조
        data = {
            "event": "image-processing.failed",
            "jobId": job_id,  # camelCase로 변경
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": {
                "code": error_code,
                "message": error_message
            }
        }
        
        # 실패 웹훅 전용 엔드포인트 사용
        failure_url = f"{webhook_url.rstrip('/')}/webhooks/image-processing/failed"
        
        return await self.send_webhook(
            failure_url,
            "image-processing.failed",
            data
        )


# 싱글톤 인스턴스
webhook_sender = WebhookSender()


async def notify_job_success(job_id: str,
                            webhook_url: Optional[str],
                            original_image_url: str,
                            processed_image_url: str,
                            person_ids: list) -> bool:
    """작업 성공 알림"""
    if not webhook_url:
        return False
    
    return await webhook_sender.send_success_webhook(
        webhook_url,
        job_id,
        original_image_url,
        processed_image_url,
        person_ids
    )


async def notify_job_failure(job_id: str,
                            webhook_url: Optional[str],
                            error_code: str = "PROCESSING_ERROR",
                            error_message: str = "Unknown error") -> bool:
    """작업 실패 알림"""
    if not webhook_url:
        return False
    
    return await webhook_sender.send_failure_webhook(
        webhook_url,
        job_id,
        error_code,
        error_message
    )
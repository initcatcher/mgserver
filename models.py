"""
데이터베이스 모델 정의
"""

from datetime import datetime
from typing import Optional, Literal
from sqlmodel import SQLModel, Field as SQLField

# 타입 정의
JobStatus = Literal["queued", "editing", "edited", "faceswap", "finalizing", "done", "failed"]
JobMode = Literal["gpt_only", "face_only", "both"]


class Job(SQLModel, table=True):
    """작업 모델"""
    id: str = SQLField(primary_key=True)
    status: str = SQLField(index=True)
    mode: str = SQLField(default="both", index=True)  # "gpt_only", "face_only", "both"
    created_at: datetime = SQLField(index=True)
    updated_at: datetime
    input_image_url: str
    prompt: str
    mapping: str = "similarity"     # "similarity" | "left_to_right" | JSON array string
    top1_only: bool = False
    threshold: float = 0.35
    error: Optional[str] = None
    
    # 새로운 API 필드들
    person_ids: Optional[str] = None  # JSON string of person IDs
    processing_type: Optional[str] = None  # "color" or "prompt"
    processing_color: Optional[str] = None
    webhook_status: Optional[str] = None  # "pending", "sent", "failed"


class JobEvent(SQLModel, table=True):
    """작업 이벤트 모델"""
    id: Optional[int] = SQLField(primary_key=True, default=None)
    job_id: str = SQLField(index=True)
    name: str
    at: datetime
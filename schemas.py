"""
API 스키마 정의 모듈
"""

from typing import Literal, Optional, List, Union
from datetime import datetime
from pydantic import BaseModel, Field


# ---------- Request Schemas ----------

class FaceRef(BaseModel):
    """얼굴 참조 모델"""
    id: Optional[str] = Field(None, description="얼굴 이미지 식별자 (선택사항)")
    source_url: str = Field(..., description="얼굴 이미지 URL")


class CreateJob(BaseModel):
    """통합 작업 생성 요청 (GPT + FaceFusion)"""
    input_image_url: str = Field(..., description="편집할 원본 이미지 URL")
    prompt: str = Field(..., description="이미지 편집을 위한 텍스트 프롬프트")
    faces: List[FaceRef] = Field(
        default_factory=list, 
        max_items=4, 
        description="얼굴 교체에 사용할 얼굴 이미지들 (최대 4개)"
    )
    mapping: Union[str, List[int]] = Field(
        default="similarity", 
        description="얼굴 매핑 방식: 'similarity'(유사도), 'left_to_right'(좌→우), 또는 인덱스 배열"
    )
    top1_only: bool = Field(
        default=False, 
        description="가장 유사한 얼굴만 교체할지 여부"
    )
    exif_strip: bool = Field(
        default=True, 
        description="EXIF 메타데이터 제거 여부"
    )
    threshold: float = Field(
        default=0.35, 
        description="얼굴 유사도 임계값 (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    use_face_mask: bool = Field(
        default=False,
        description="얼굴 보존 마스크 사용 여부 (얼굴/머리 영역 보존, 배경만 편집)"
    )
    mask_feather_pixels: int = Field(
        default=12,
        description="마스크 경계 부드럽게 처리할 픽셀 수",
        ge=0,
        le=50
    )
    face_expand_ratio: float = Field(
        default=0.3,
        description="얼굴 영역 확장 비율 (머리카락 포함을 위해)",
        ge=0.0,
        le=1.0
    )


class CreateGPTJob(BaseModel):
    """GPT 전용 작업 생성 요청"""
    input_image_url: str = Field(..., description="편집할 원본 이미지 URL")
    prompt: str = Field(..., description="이미지 편집을 위한 텍스트 프롬프트")
    exif_strip: bool = Field(
        default=True, 
        description="EXIF 메타데이터 제거 여부"
    )
    use_face_mask: bool = Field(
        default=False,
        description="얼굴 보존 마스크 사용 여부 (얼굴/머리 영역 보존, 배경만 편집)"
    )
    mask_feather_pixels: int = Field(
        default=12,
        description="마스크 경계 부드럽게 처리할 픽셀 수",
        ge=0,
        le=50
    )
    face_expand_ratio: float = Field(
        default=0.3,
        description="얼굴 영역 확장 비율 (머리카락 포함을 위해)",
        ge=0.0,
        le=1.0
    )


class CreateFaceJob(BaseModel):
    """FaceFusion 전용 작업 생성 요청"""
    input_image_url: str = Field(..., description="편집할 원본 이미지 URL")
    faces: List[FaceRef] = Field(
        ..., 
        min_items=1,
        max_items=4, 
        description="얼굴 교체에 사용할 얼굴 이미지들 (1-4개)"
    )
    mapping: Union[str, List[int]] = Field(
        default="similarity", 
        description="얼굴 매핑 방식: 'similarity'(유사도), 'left_to_right'(좌→우), 또는 인덱스 배열"
    )
    top1_only: bool = Field(
        default=False, 
        description="가장 유사한 얼굴만 교체할지 여부"
    )
    exif_strip: bool = Field(
        default=True, 
        description="EXIF 메타데이터 제거 여부"
    )
    threshold: float = Field(
        default=0.35, 
        description="얼굴 유사도 임계값 (0.0-1.0)",
        ge=0.0,
        le=1.0
    )


# ---------- Response Schemas ----------

class JobResponse(BaseModel):
    """작업 응답 모델"""
    job_id: str = Field(..., description="작업 ID")
    status: str = Field(..., description="작업 상태")
    mode: str = Field(..., description="작업 모드: gpt_only, face_only, both")
    progress: int = Field(..., description="진행률 (0-100)")
    steps: List[dict] = Field(default_factory=list, description="처리 단계 기록")
    artifacts: dict = Field(default_factory=dict, description="생성된 파일 URL들")
    meta: dict = Field(default_factory=dict, description="메타데이터 URL들")
    error: Optional[str] = Field(None, description="에러 메시지")
    links: dict = Field(default_factory=dict, description="관련 링크들")


class JobCreateResponse(BaseModel):
    """작업 생성 응답 모델"""
    job_id: str = Field(..., description="생성된 작업 ID")
    mode: str = Field(..., description="작업 모드")
    status: str = Field(default="queued", description="초기 상태")
    message: str = Field(default="Job created successfully", description="응답 메시지")
    links: dict = Field(default_factory=dict, description="관련 링크들")


class UploadResponse(BaseModel):
    """파일 업로드 응답 모델"""
    success: bool = Field(..., description="성공 여부")
    message: str = Field(..., description="응답 메시지")
    data: dict = Field(..., description="업로드 파일 정보")
    links: dict = Field(default_factory=dict, description="관련 링크들")


class FileListResponse(BaseModel):
    """파일 목록 응답 모델"""
    success: bool = Field(..., description="성공 여부")
    data: dict = Field(..., description="파일 목록 데이터")


class FileInfoResponse(BaseModel):
    """파일 정보 응답 모델"""
    success: bool = Field(..., description="성공 여부")
    message: str = Field(..., description="응답 메시지")
    data: dict = Field(..., description="파일 정보")


class HealthResponse(BaseModel):
    """헬스체크 응답 모델"""
    status: str = Field(default="healthy", description="서버 상태")
    upload_dir: str = Field(..., description="업로드 디렉토리")
    jobs_dir: str = Field(..., description="작업 디렉토리")
    mode_support: List[str] = Field(
        default=["gpt_only", "face_only", "both"],
        description="지원하는 작업 모드들"
    )
    active_tasks: Optional[int] = Field(None, description="활성 백그라운드 태스크 수")


# ---------- New API Schemas ----------

class ProcessingOptions(BaseModel):
    """이미지 처리 옵션"""
    type: Literal["color", "prompt"] = Field(..., description="처리 타입")
    prompt: Optional[str] = Field(None, description="프롬프트 (type=prompt일 때)")
    color: Optional[str] = Field(None, description="색상 (type=color일 때)")

class CreateImageJob(BaseModel):
    """새로운 이미지 처리 작업 요청"""
    image_url: str = Field(..., description="처리할 이미지 URL")
    person_ids: List[str] = Field(..., min_items=1, description="단체사진에 포함된 유저 ID들")
    processing_options: ProcessingOptions = Field(..., description="처리 옵션")

class ImageJobResponse(BaseModel):
    """이미지 작업 응답"""
    data: dict = Field(..., description="응답 데이터")

class ErrorDetail(BaseModel):
    """에러 상세 정보"""
    code: str = Field(..., description="에러 코드")
    message: str = Field(..., description="에러 메시지")
    details: Optional[dict] = Field(None, description="추가 상세 정보")

class ErrorResponse(BaseModel):
    """에러 응답"""
    error: ErrorDetail = Field(..., description="에러 정보")

# ---------- Type Definitions ----------

JobStatus = Literal["queued", "editing", "edited", "faceswap", "finalizing", "done", "failed"]
JobMode = Literal["gpt_only", "face_only", "both"]
ProcessingType = Literal["color", "prompt"]
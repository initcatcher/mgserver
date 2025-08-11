from __future__ import annotations
import os, json, uuid, logging, mimetypes, asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, File, UploadFile, Body
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel, Field as SQLField, Session, create_engine, select
from dotenv import load_dotenv
from PIL import Image

# 모듈화된 코드 import
from schemas import (
    CreateJob, CreateGPTJob, CreateFaceJob, FaceRef,
    JobResponse, JobCreateResponse, UploadResponse,
    FileListResponse, FileInfoResponse, HealthResponse,
    # 새로운 API 스키마
    CreateImageJob, ImageJobResponse, ErrorResponse, ErrorDetail, ProcessingOptions
)
from pipelines import gpt_only_pipeline, face_only_pipeline, full_pipeline
from utils import (
    make_job_id, to_public_url, is_allowed_file, 
    generate_unique_filename, progress_of_status
)

# ---------- env ----------
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

MEDIA_ROOT      = Path(os.getenv("MEDIA_ROOT", "/home/catch/media"))
JOBS_DIR        = Path(os.getenv("JOBS_DIR", str(MEDIA_ROOT / "jobs")))
UPLOAD_DIR      = MEDIA_ROOT / "uploads"
PUBLIC_BASE     = os.getenv("PUBLIC_BASE_PATH", "/media")
DOMAIN_BASE_URL = os.getenv("DOMAIN_BASE_URL", "")  # e.g. https://image.nearzoom.store
USE_OPENAI      = os.getenv("USE_OPENAI", "0") == "1"
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
FF_WRAPPER      = os.getenv("FF_WRAPPER", "/home/catch/facefusion/ff.sh")
FF_RUNNER       = os.getenv("FF_RUNNER", "/home/catch/facefusion/ff_runner.py")
GPU_CONCURRENCY = int(os.getenv("GPU_CONCURRENCY", "1"))
SIM_THRESHOLD   = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))

# 업로드 설정
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

DB_PATH = Path(__file__).with_name("jobs.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

# ---------- logging ----------
def setup_logging():
    """로깅 시스템 설정"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(MEDIA_ROOT / "server.log", encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ---------- models ----------
JobStatus = Literal["queued","editing","edited","faceswap","finalizing","done","failed"]

class Job(SQLModel, table=True):
    id: str = SQLField(primary_key=True)
    status: str = SQLField(index=True)
    mode: str = SQLField(default="both", index=True)  # "gpt_only", "face_only", "both"
    created_at: datetime = SQLField(index=True)
    updated_at: datetime
    input_image_url: str
    prompt: str
    mapping: str = "similarity"     # "similarity" | "left_to_right" | JSON array string
    top1_only: bool = False
    threshold: float = SIM_THRESHOLD
    error: Optional[str] = None
    # 새로운 API 필드들
    person_ids: Optional[str] = None  # JSON string of person IDs
    processing_type: Optional[str] = None  # "color" or "prompt"
    processing_color: Optional[str] = None
    webhook_url: Optional[str] = None
    webhook_status: Optional[str] = None  # "pending", "sent", "failed"

class JobEvent(SQLModel, table=True):
    id: Optional[int] = SQLField(primary_key=True, default=None)
    job_id: str = SQLField(index=True)
    name: str
    at: datetime

def init_db():
    SQLModel.metadata.create_all(engine)

# ---------- 스키마는 schemas.py에서 import됨 ----------

# ---------- utils ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def make_job_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"

def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id

def ensure_tree(job_id: str) -> dict[str, Path]:
    base = job_dir(job_id)
    paths = {
        "base": base,
        "input": base/"input",
        "faces": base/"faces",
        "gpt": base/"gpt",
        "final": base/"final",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths

def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8")

def to_public_url(abs_path: Path) -> str:
    abs_str = str(abs_path)
    media_root_str = str(MEDIA_ROOT)
    assert abs_str.startswith(media_root_str), f"path not under MEDIA_ROOT: {abs_path}"
    rel = abs_str[len(media_root_str):]
    rel_url = f"{PUBLIC_BASE}{rel}"
    if DOMAIN_BASE_URL:
        return f"{DOMAIN_BASE_URL.rstrip('/')}{rel_url}"
    return rel_url

# download_to, strip_exif는 pipelines.py로 이동됨 (utils로 분리 필요)

def record_event(job_id: str, name: str):
    with Session(engine) as s:
        s.add(JobEvent(job_id=job_id, name=name, at=now_utc()))
        s.exec(select(Job).where(Job.id==job_id)).one().updated_at = now_utc()
        s.commit()

def set_status(job_id: str, status: JobStatus, error: Optional[str]=None):
    with Session(engine) as s:
        j = s.exec(select(Job).where(Job.id==job_id)).one()
        j.status = status
        j.updated_at = now_utc()
        if error:
            j.error = error
        s.add(j)
        s.add(JobEvent(job_id=job_id, name=status, at=now_utc()))
        s.commit()

# write_params_and_prompt, copy_as_placeholder는 pipelines.py에 있음

# ---------- upload utils ----------
def is_allowed_file(filename: str, content_type: str = None) -> bool:
    """파일이 허용된 형식인지 확인"""
    if not filename:
        return False
    
    file_ext = Path(filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False
    
    if content_type and not content_type.startswith('image/'):
        return False
    
    return True

def generate_unique_filename(original_filename: str) -> str:
    """중복 방지를 위한 고유 파일명 생성 (원본 파일명 유지)"""
    file_path = Path(original_filename)
    name_without_ext = file_path.stem
    file_ext = file_path.suffix.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"{name_without_ext}_{timestamp}_{unique_id}{file_ext}"

# ---------- GPT edit, FaceFusion runner는 pipelines.py로 이동됨 ----------

# ---------- response assembler ----------
def job_response(job: Job):
    base = job_dir(job.id)
    input_png = base/"input"/"input.png"
    edited_png = base/"gpt"/"edited.png"
    final_png = base/"final"/"result.png"

    artifacts = {
        "input":   to_public_url(input_png)   if input_png.exists() else None,
        "gpt":     to_public_url(edited_png)  if edited_png.exists() else None,
        "final":   to_public_url(final_png)   if final_png.exists() else None,
    }
    with Session(engine) as s:
        evs = s.exec(select(JobEvent).where(JobEvent.job_id==job.id).order_by(JobEvent.at)).all()
    steps=[{"name":e.name,"at":e.at.isoformat()} for e in evs]

    meta = {
        "params": to_public_url(base/"params.json") if (base/"params.json").exists() else None,
        "prompt": to_public_url(base/"prompt.txt")  if (base/"prompt.txt").exists() else None,
        "logs":   to_public_url(base/"logs.txt")    if (base/"logs.txt").exists() else None,
    }

    return {
        "job_id": job.id,
        "status": job.status,
        "mode": job.mode,  # mode 필드 추가
        "progress": _progress_of(job.status),
        "steps": steps,
        "artifacts": artifacts,
        "meta": meta,
        "error": job.error,
        "links": {"self": f"/jobs/{job.id}", "artifacts": f"/media/jobs/{job.id}/"}
    }

def _progress_of(status: str) -> int:
    order = ["queued","editing","edited","faceswap","finalizing","done","failed"]
    try: return int(100 * order.index(status) / (len(order)-1))
    except: return 0

# ---------- app ----------
app = FastAPI(
    title="AI 이미지 처리 서버", 
    version="1.0.0",
    description="""
    AI를 활용한 이미지 편집 및 얼굴 교체 서비스

    ## 주요 기능
    - **GPT 이미지 편집**: OpenAI GPT를 이용한 텍스트 기반 이미지 편집
    - **얼굴 교체**: FaceFusion을 이용한 얼굴 교체 기능
    - **작업 추적**: 실시간 작업 상태 모니터링
    
    ## 사용 방법
    1. `/jobs` 엔드포인트로 작업 생성
    2. 반환된 `job_id`로 진행상황 추적
    3. 완료 후 결과 이미지 다운로드
    """,
    contact={
        "name": "AI Image Server",
        "url": "http://localhost/docs",
    }
)

@app.on_event("startup")
def _startup():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

@app.post("/jobs", status_code=201,
         summary="이미지 처리 작업 (새로운 API)",
         description="Person ID 기반 이미지 처리 작업을 생성합니다.",
         response_model=ImageJobResponse,
         responses={
             400: {"model": ErrorResponse, "description": "Bad Request"},
             404: {"model": ErrorResponse, "description": "Not Found"}
         })
async def create_image_job(payload: CreateImageJob = Body(...)):
    """새로운 형식의 이미지 처리 작업"""
    job_id = make_job_id()
    logger.info(f"Creating image job: {job_id} with person_ids: {payload.person_ids}")
    
    # person_ids 검증 (예시 - 실제로는 DB에서 확인)
    if not payload.person_ids:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "person_ids must contain at least one valid person ID",
                    "details": {}
                }
            }
        )
    
    # processing_options 검증
    if payload.processing_options.type == "prompt" and not payload.processing_options.prompt:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "prompt is required when type is 'prompt'",
                    "details": {}
                }
            }
        )
    
    if payload.processing_options.type == "color" and not payload.processing_options.color:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "color is required when type is 'color'",
                    "details": {}
                }
            }
        )
    
    # 프롬프트 생성 (color 타입인 경우)
    if payload.processing_options.type == "color":
        prompt = f"Change the background to {payload.processing_options.color} theme, preserve all people and faces"
    else:
        prompt = payload.processing_options.prompt
    
    # DB에 작업 저장
    with Session(engine) as s:
        j = Job(
            id=job_id,
            status="queued",
            mode="gpt_only",  # 기본적으로 GPT 편집만 사용
            created_at=now_utc(),
            updated_at=now_utc(),
            input_image_url=payload.image_url,
            prompt=prompt,
            mapping="similarity",
            top1_only=False,
            threshold=SIM_THRESHOLD,
            # 새로운 필드들
            person_ids=json.dumps(payload.person_ids),
            processing_type=payload.processing_options.type,
            processing_color=payload.processing_options.color,
            webhook_url=payload.webhook_url,
            webhook_status="pending" if payload.webhook_url else None
        )
        s.add(j)
        s.add(JobEvent(job_id=job_id, name="queued", at=now_utc()))
        s.commit()
    
    # 비동기 파이프라인 실행 (얼굴 보존 마스크 사용)
    asyncio.create_task(
        process_image_with_webhook(
            job_id,
            payload.image_url,
            prompt,
            payload.person_ids,
            payload.webhook_url
        )
    )
    
    # 표준 응답
    return ImageJobResponse(
        data={
            "job_id": job_id,
            "status": "queued",
            "created_at": now_utc().isoformat()
        }
    )


# 웹훅 통합 파이프라인 함수
async def process_image_with_webhook(job_id: str, image_url: str, prompt: str, 
                                    person_ids: list, webhook_url: Optional[str]):
    """웹훅 알림이 포함된 이미지 처리 파이프라인"""
    try:
        # GPT 편집 실행 (얼굴 보존 마스크 사용)
        await gpt_only_pipeline(
            job_id,
            image_url,
            prompt,
            exif_strip=True,
            use_face_mask=True,  # 얼굴 보존
            mask_feather_pixels=15,
            face_expand_ratio=0.6,  # 머리카락까지 포함
            set_status_func=set_status,
            record_event_func=record_event
        )
        
        # 성공 시 웹훅 전송
        if webhook_url:
            from webhook import notify_job_success
            base = job_dir(job_id)
            result_image = base / "final" / "result.png"
            if result_image.exists():
                processed_url = to_public_url(result_image)
                await notify_job_success(
                    job_id,
                    webhook_url,
                    image_url,
                    processed_url,
                    person_ids
                )
                # 웹훅 상태 업데이트
                with Session(engine) as s:
                    job = s.exec(select(Job).where(Job.id == job_id)).one()
                    job.webhook_status = "sent"
                    s.commit()
    
    except Exception as e:
        logger.error(f"Image processing failed for {job_id}: {str(e)}")
        set_status(job_id, "failed", error=str(e))
        
        # 실패 시 웹훅 전송
        if webhook_url:
            from webhook import notify_job_failure
            await notify_job_failure(
                job_id,
                webhook_url,
                error_code="PROCESSING_ERROR",
                error_message=str(e)
            )
            # 웹훅 상태 업데이트
            with Session(engine) as s:
                job = s.exec(select(Job).where(Job.id == job_id)).one()
                job.webhook_status = "sent"
                s.commit()


@app.post("/jobs/gpt-edit", status_code=201,
         summary="GPT 이미지 편집 작업",
         description="OpenAI GPT를 사용한 이미지 편집만 수행합니다.",
         response_model=JobCreateResponse)
async def create_gpt_job(payload: CreateGPTJob = Body(...)):
    """GPT 이미지 편집 전용 엔드포인트"""
    job_id = make_job_id()
    logger.info(f"Creating GPT-only job: {job_id}")
    
    with Session(engine) as s:
        j = Job(
            id=job_id, 
            status="queued",
            mode="gpt_only",
            created_at=now_utc(), 
            updated_at=now_utc(),
            input_image_url=payload.input_image_url,
            prompt=payload.prompt,
            mapping="similarity",
            top1_only=False,
            threshold=SIM_THRESHOLD
        )
        s.add(j)
        s.add(JobEvent(job_id=job_id, name="queued", at=now_utc()))
        s.commit()
    
    # asyncio.create_task를 사용하여 비동기 실행
    # 마스크 파라미터 기본값 처리
    use_face_mask = getattr(payload, 'use_face_mask', False)
    mask_feather_pixels = getattr(payload, 'mask_feather_pixels', 12)
    face_expand_ratio = getattr(payload, 'face_expand_ratio', 0.3)
    
    # 백그라운드에서 실행 (블로킹 없음)
    asyncio.create_task(
        gpt_only_pipeline(
            job_id, 
            payload.input_image_url, 
            payload.prompt,
            payload.exif_strip,
            use_face_mask,
            mask_feather_pixels,
            face_expand_ratio,
            set_status,
            record_event
        )
    )
    
    return JobCreateResponse(
        job_id=job_id,
        mode="gpt_only",
        status="queued",
        message="GPT image editing job created successfully",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@app.post("/jobs/face-swap", status_code=201,
         summary="얼굴 교체 작업",
         description="FaceFusion을 사용한 얼굴 교체만 수행합니다.",
         response_model=JobCreateResponse)
async def create_face_job(payload: CreateFaceJob = Body(...)):
    """FaceFusion 얼굴 교체 전용 엔드포인트"""
    job_id = make_job_id()
    logger.info(f"Creating face-swap job: {job_id}")
    
    with Session(engine) as s:
        mapping_str = payload.mapping if isinstance(payload.mapping, str) else json.dumps(payload.mapping)
        j = Job(
            id=job_id,
            status="queued",
            mode="face_only",
            created_at=now_utc(),
            updated_at=now_utc(),
            input_image_url=payload.input_image_url,
            prompt="",  # Face-only는 프롬프트 불필요
            mapping=mapping_str,
            top1_only=payload.top1_only,
            threshold=payload.threshold
        )
        s.add(j)
        s.add(JobEvent(job_id=job_id, name="queued", at=now_utc()))
        s.commit()
    
    # asyncio.create_task를 사용하여 비동기 실행
    asyncio.create_task(
        face_only_pipeline(
            job_id,
            payload.input_image_url,
            payload.faces,
            payload.mapping,
            payload.top1_only,
            payload.threshold,
            payload.exif_strip,
            set_status,
            record_event
        )
    )
    
    return JobCreateResponse(
        job_id=job_id,
        mode="face_only",
        status="queued",
        message="Face swap job created successfully",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )


@app.post("/jobs/legacy", status_code=201, 
         summary="통합 작업 생성 (GPT + FaceFusion)", 
         description="AI 이미지 편집과 얼굴 교체를 모두 수행합니다.",
         response_model=JobCreateResponse)
async def create_job(payload: CreateJob = Body(...)):
    """통합 작업 생성 - GPT 편집과 FaceFusion을 모두 수행"""
    job_id = make_job_id()
    logger.info(f"Creating full pipeline job: {job_id}")
    
    with Session(engine) as s:
        j = Job(
            id=job_id, 
            status="queued",
            mode="both",  # 통합 모드
            created_at=now_utc(), 
            updated_at=now_utc(),
            input_image_url=payload.input_image_url,
            prompt=payload.prompt, 
            mapping=payload.mapping if isinstance(payload.mapping, str) else json.dumps(payload.mapping),
            top1_only=payload.top1_only, 
            threshold=payload.threshold
        )
        s.add(j)
        s.add(JobEvent(job_id=job_id, name="queued", at=now_utc()))
        s.commit()

    # asyncio.create_task를 사용하여 비동기 실행
    asyncio.create_task(
        full_pipeline(job_id, payload, set_status, record_event)
    )

    return JobCreateResponse(
        job_id=job_id,
        mode="both",
        status="queued",
        message="Full pipeline job created successfully (GPT + FaceFusion)",
        links={
            "self": f"/jobs/{job_id}",
            "artifacts": f"/media/jobs/{job_id}/"
        }
    )

@app.get("/jobs/{job_id}",
         summary="작업 상태 조회",
         description="작업 ID로 진행상황과 결과를 조회합니다.")
def get_job(job_id: str):
    with Session(engine) as s:
        job = s.exec(select(Job).where(Job.id==job_id)).first()
        if not job:
            raise HTTPException(404, "job not found")
    return job_response(job)

@app.get("/", 
         summary="서버 정보", 
         description="서버 상태를 확인합니다.")
def root():
    return {"ok": True}

@app.get("/health",
         summary="헬스 체크",
         description="서버 상태를 확인합니다.",
         response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy", 
        upload_dir=str(UPLOAD_DIR), 
        jobs_dir=str(JOBS_DIR),
        mode_support=["gpt_only", "face_only", "both"]
    )

@app.post("/upload",
          summary="파일 업로드",
          description="이미지 파일을 업로드합니다.")
async def upload_photo(file: UploadFile = File(...)):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")
        
        if not is_allowed_file(file.filename, file.content_type):
            raise HTTPException(
                status_code=400, 
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        content = await file.read()
        
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        unique_filename = generate_unique_filename(file.filename)
        file_path = UPLOAD_DIR / unique_filename
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        file_url = f"{PUBLIC_BASE}/uploads/{unique_filename}"
        if DOMAIN_BASE_URL:
            file_url = f"{DOMAIN_BASE_URL.rstrip('/')}{file_url}"
        
        # 이미지 메타데이터 추출
        image_metadata = {}
        try:
            with Image.open(file_path) as img:
                image_metadata = {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode
                }
        except Exception as e:
            logger.warning(f"Could not extract image metadata: {str(e)}")
        
        logger.info(f"File uploaded: {unique_filename} ({len(content)} bytes)")
        
        response_data = {
            "success": True,
            "message": "File uploaded successfully",
            "data": {
                "original_filename": file.filename,
                "saved_filename": unique_filename,
                "file_url": file_url,
                "file_size": len(content),
                "content_type": file.content_type,
                "upload_time": datetime.now().isoformat(),
                "image_metadata": image_metadata
            },
            "links": {
                "download": file_url,
                "info": f"/uploads/{unique_filename}",
                "list": "/uploads"
            }
        }
        
        return JSONResponse(
            status_code=200,
            content=response_data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Upload-Success": "true",
                "X-File-Size": str(len(content)),
                "X-File-Type": file.content_type or "unknown"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/uploads",
         summary="업로드 파일 목록",
         description="업로드된 파일 목록을 조회합니다.")
async def list_uploads():
    try:
        files = []
        for filename in os.listdir(UPLOAD_DIR):
            file_path = UPLOAD_DIR / filename
            if file_path.is_file():
                stat = file_path.stat()
                file_url = f"{PUBLIC_BASE}/uploads/{filename}"
                if DOMAIN_BASE_URL:
                    file_url = f"{DOMAIN_BASE_URL.rstrip('/')}{file_url}"
                    
                files.append({
                    "filename": filename,
                    "file_url": file_url,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        files.sort(key=lambda x: x["created"], reverse=True)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "files": files,
                    "total_count": len(files)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to list files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")

@app.get("/uploads/{filename}",
         summary="업로드 파일 정보",
         description="특정 업로드 파일의 정보를 조회합니다.")
async def check_file(filename: str):
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"File '{filename}' not found"
            )
        
        stat = file_path.stat()
        file_url = f"{PUBLIC_BASE}/uploads/{filename}"
        if DOMAIN_BASE_URL:
            file_url = f"{DOMAIN_BASE_URL.rstrip('/')}{file_url}"
            
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "File found",
                "data": {
                    "filename": filename,
                    "file_url": file_url,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "content_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"
                }
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

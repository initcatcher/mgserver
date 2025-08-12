"""
리팩토링된 FastAPI 메인 애플리케이션
"""

import logging
import os
import shutil
import uuid
import mimetypes
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Local module imports
from api.jobs import router as jobs_router
from schemas import HealthResponse
from services.face_queue import face_queue

# 환경 변수 로드
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

# 환경 설정
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/home/catch/media"))
JOBS_DIR = Path(os.getenv("JOBS_DIR", str(MEDIA_ROOT / "jobs")))
UPLOAD_DIR = MEDIA_ROOT / "uploads"

# 업로드 설정
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 로깅 설정
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

# 업로드 유틸리티 함수
def is_allowed_file(filename: str, content_type: str = None) -> bool:
    """허용된 파일 형식인지 확인"""
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

# FastAPI 앱 생성
app = FastAPI(
    title="AI 이미지 처리 서버 (리팩토링)",
    version="2.0.0",
    description="""
    리팩토링된 AI 이미지 처리 서버
    
    ## 주요 개선사항
    - 모듈화된 구조
    - 비블로킹 백그라운드 처리
    - 새로운 API 형식 지원
    
    ## API 엔드포인트
    - `POST /jobs`: 새로운 person_ids 기반 이미지 처리
    - `POST /jobs/gpt-edit`: GPT 이미지 편집
    - `POST /jobs/face-swap`: 얼굴 교체
    - `POST /jobs/legacy`: 기존 통합 처리
    """,
    contact={
        "name": "AI Image Server",
        "url": "http://localhost/docs",
    }
)

# CORS 설정 - 모든 오리진 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize on server start"""
    # Create directories
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Start face queue worker
    await face_queue.start()
    
    logger.info("Server started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on server shutdown"""
    # Stop face queue worker
    await face_queue.stop()
    
    # Shutdown GPT processor
    from services.gpt_processor import gpt_processor
    gpt_processor.shutdown()
    
    logger.info("Server shutdown completed")


# 라우터 등록
app.include_router(jobs_router)


# 기본 엔드포인트
@app.get("/", summary="서버 정보")
def root():
    """루트 엔드포인트"""
    return {"message": "AI Image Processing Server (Refactored)", "version": "2.0.0"}


@app.get("/health", response_model=HealthResponse, summary="Health check")
def health_check():
    """Health check endpoint"""
    from services.job_manager import job_manager
    
    queue_status = job_manager.get_queue_status()
    
    return HealthResponse(
        status="healthy",
        upload_dir=str(UPLOAD_DIR),
        jobs_dir=str(JOBS_DIR),
        mode_support=["gpt_only", "face_only", "both"],
        active_tasks=queue_status.get("gpt_processing", 0) + queue_status.get("face_processing", 0)
    )


@app.post("/upload", summary="파일 업로드")
async def upload_photo(file: UploadFile = File(...)):
    """파일 업로드 엔드포인트"""
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
        
        file_url = f"https://image.nearzoom.store/media/uploads/{unique_filename}"
        file_size = len(content)
        
        logger.info(f"File uploaded: {file_path}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "File uploaded successfully",
                "data": {
                    "original_filename": file.filename,
                    "saved_filename": unique_filename,
                    "file_url": file_url,
                    "file_size": file_size,
                    "content_type": file.content_type,
                    "upload_time": datetime.now().isoformat()
                }
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/uploads", summary="업로드된 파일 목록")
async def list_uploads():
    """업로드된 파일 목록 조회"""
    try:
        files = []
        for file_path in UPLOAD_DIR.glob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "filename": file_path.name,
                    "file_url": f"https://image.nearzoom.store/media/uploads/{file_path.name}",
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


@app.get("/uploads/{filename}", summary="파일 정보 확인")
async def check_file(filename: str):
    """업로드된 파일 정보 확인"""
    try:
        file_path = UPLOAD_DIR / filename
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"File '{filename}' not found"
            )
        
        stat = file_path.stat()
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "File found",
                "data": {
                    "filename": filename,
                    "file_url": f"https://image.nearzoom.store/media/uploads/{filename}",
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


# 전역 예외 처리
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """전역 예외 처리기"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred"
            }
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
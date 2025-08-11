from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
import mimetypes

app = FastAPI(title="Photo Upload Server", version="1.0.0")

UPLOAD_DIR = "/home/catch/media/uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

os.makedirs(UPLOAD_DIR, exist_ok=True)

def is_allowed_file(filename: str, content_type: str = None) -> bool:
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

@app.get("/")
async def root():
    return {"message": "Photo Upload Server is running", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "upload_dir": UPLOAD_DIR}

@app.post("/upload")
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
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        file_url = f"/media/uploads/{unique_filename}"
        file_size = len(content)
        
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
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/uploads")
async def list_uploads():
    try:
        files = []
        for filename in os.listdir(UPLOAD_DIR):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(file_path):
                stat = os.stat(file_path)
                files.append({
                    "filename": filename,
                    "file_url": f"/media/uploads/{filename}",
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
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")

@app.get("/uploads/{filename}")
async def check_file(filename: str):
    try:
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"File '{filename}' not found"
            )
        
        stat = os.stat(file_path)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "File found",
                "data": {
                    "filename": filename,
                    "file_url": f"/media/uploads/{filename}",
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
        raise HTTPException(status_code=500, detail=f"Failed to check file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
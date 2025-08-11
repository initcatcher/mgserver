"""
AI 이미지 처리 파이프라인 모듈
- GPT 전용 파이프라인
- FaceFusion 전용 파이프라인
- 통합 파이프라인 (GPT + FaceFusion)
"""

import os
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union
import logging

import httpx
from PIL import Image
from openai import OpenAI
from sqlmodel import Session, select
from dotenv import load_dotenv

from schemas import CreateJob, FaceRef

logger = logging.getLogger(__name__)

# .env 파일 로드
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

# 환경 변수
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", "/home/catch/media"))
JOBS_DIR = Path(os.getenv("JOBS_DIR", str(MEDIA_ROOT / "jobs")))
USE_OPENAI = os.getenv("USE_OPENAI", "0") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FF_WRAPPER = os.getenv("FF_WRAPPER", "/home/catch/facefusion/ff.sh")
FF_RUNNER = os.getenv("FF_RUNNER", "/home/catch/facefusion/ff_runner.py")
SIM_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))


def now_utc() -> datetime:
    """현재 UTC 시간 반환"""
    return datetime.now(timezone.utc)


def job_dir(job_id: str) -> Path:
    """작업 디렉토리 경로 반환"""
    return JOBS_DIR / job_id


def ensure_tree(job_id: str) -> dict[str, Path]:
    """작업 디렉토리 구조 생성"""
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
    """텍스트 파일 작성"""
    path.write_text(text, encoding="utf-8")


def write_params_and_prompt(base: Path, params: dict, prompt: str = None):
    """파라미터와 프롬프트 저장"""
    if prompt:
        write_text(base/"prompt.txt", prompt)
    (base/"params.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def download_to(url: str, dest: Path):
    """URL에서 파일 다운로드"""
    timeout = httpx.Timeout(60.0, read=120.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"download failed: {url} ({r.status_code})")
        dest.write_bytes(r.content)


async def strip_exif(in_path: Path, out_path: Path):
    """EXIF 메타데이터 제거 - 비동기"""
    import asyncio
    
    def _strip_exif_sync():
        with Image.open(in_path) as im:
            im.load()
            data = im.convert("RGB") if im.mode not in ("RGB","RGBA") else im.copy()
            data.save(out_path, format="PNG")
    
    await asyncio.to_thread(_strip_exif_sync)


async def download_and_strip(url: str, output_dir: Path, exif_strip: bool = True) -> Path:
    """이미지 다운로드 및 EXIF 제거"""
    input_dl = output_dir / "input_src"
    await download_to(url, input_dl)
    
    input_png = output_dir / "input.png"
    if exif_strip:
        await strip_exif(input_dl, input_png)
        input_dl.unlink(missing_ok=True)
    else:
        import asyncio
        await asyncio.to_thread(shutil.move, input_dl, input_png)
    
    return input_png


async def download_faces(faces: List[FaceRef], faces_dir: Path):
    """얼굴 이미지들 다운로드"""
    for i, f in enumerate(faces[:4]):
        dest_raw = faces_dir/f"f{i}_src"
        await download_to(f.source_url, dest_raw)
        dest_png = faces_dir/f"f{i}.png"
        await strip_exif(dest_raw, dest_png)
        dest_raw.unlink(missing_ok=True)


async def copy_as_placeholder(src: Path, dst: Path):
    """파일 복사 (플레이스홀더용) - 비동기"""
    import asyncio
    await asyncio.to_thread(shutil.copy2, src, dst)


# ---------- GPT 이미지 편집 ----------
async def gpt_edit_image(input_png: Path, prompt: str, out_png: Path, 
                        use_face_mask: bool = False, mask_feather_pixels: int = 12, 
                        face_expand_ratio: float = 0.3):
    """OpenAI GPT를 이용한 이미지 편집"""
    if not OPENAI_API_KEY:
        await copy_as_placeholder(input_png, out_png)
        logger.info("OpenAI API key not set, copying original image")
        return
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # 마스크 생성 (필요한 경우)
        mask_file = None
        if use_face_mask:
            from face_mask import create_face_preservation_mask
            logger.info("Creating face preservation mask...")
            mask_file = await create_face_preservation_mask(
                input_png, mask_feather_pixels, face_expand_ratio
            )
            if mask_file:
                logger.info(f"Face mask created: {mask_file}")
            else:
                logger.warning("Failed to create face mask, proceeding without mask")
        
        # 이미지를 1024x1024로 리사이즈하고 RGBA로 변환 (비동기)
        def _process_image_sync():
            with Image.open(input_png) as img:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                
                # OpenAI gpt-image-1은 RGBA 형식을 요구함
                if img.mode != 'RGBA':
                    if img.mode in ('RGB', 'L', 'P'):
                        # RGB나 다른 형식을 RGBA로 변환 (완전 불투명)
                        img = img.convert('RGBA')
                    elif img.mode == 'LA':
                        # LA (grayscale + alpha)를 RGBA로 변환
                        img = img.convert('RGBA')
                    else:
                        # 기타 형식을 RGBA로 변환
                        img = img.convert('RGBA')
                
                temp_input = input_png.parent / "temp_for_openai.png"
                img.save(temp_input, format='PNG')
                return temp_input
        
        import asyncio
        temp_input = await asyncio.to_thread(_process_image_sync)
        
        # OpenAI API 호출 (gpt-image-1 모델 사용)
        with open(temp_input, "rb") as image_file:
            edit_params = {
                "image": image_file,
                "prompt": prompt,
                "model": "gpt-image-1",
                "n": 1,
                "size": "1024x1024"
            }
            
            # 마스크 파일이 있으면 추가
            if mask_file and mask_file.exists():
                with open(mask_file, "rb") as mask_image_file:
                    edit_params["mask"] = mask_image_file
                    logger.info("Using face preservation mask for GPT edit")
                    response = client.images.edit(**edit_params)
            else:
                response = client.images.edit(**edit_params)
        
        # 결과 이미지 처리 (gpt-image-1은 base64, dall-e-2는 URL 반환)
        response_data = response.data[0]
        
        if hasattr(response_data, 'b64_json') and response_data.b64_json:
            # Base64 형식 (gpt-image-1)
            import base64
            image_data = base64.b64decode(response_data.b64_json)
            out_png.write_bytes(image_data)
            logger.info("Image received as base64 data")
        elif hasattr(response_data, 'url') and response_data.url:
            # URL 형식 (dall-e-2)
            async with httpx.AsyncClient() as http_client:
                img_response = await http_client.get(response_data.url)
                if img_response.status_code == 200:
                    out_png.write_bytes(img_response.content)
                    logger.info(f"Image downloaded from URL: {response_data.url}")
                else:
                    raise RuntimeError(f"Failed to download result image: {img_response.status_code}")
        else:
            raise RuntimeError(f"No valid image data found in response. Available attributes: {dir(response_data)}")
        
        # 임시 파일 정리
        temp_input.unlink(missing_ok=True)
        if mask_file and mask_file.exists():
            mask_file.unlink(missing_ok=True)
            logger.info("Face mask file cleaned up")
        
        mask_info = " with face mask" if use_face_mask and mask_file else ""
        logger.info(f"GPT edit completed{mask_info} for prompt: {prompt[:50]}...")
        
    except Exception as e:
        await copy_as_placeholder(input_png, out_png)
        logger.error(f"OpenAI image edit failed: {str(e)}")
        raise RuntimeError(f"OpenAI image edit failed: {str(e)}")


# ---------- FaceFusion 실행 ----------
async def run_facefusion_runner(edited_png: Path, faces_dir: Path, out_png: Path,
                          mapping: str, top1_only: bool = False, threshold: float = SIM_THRESHOLD):
    """FaceFusion CLI를 이용한 얼굴 교체 (비동기)"""
    import asyncio
    
    # 얼굴 이미지 파일들 확인
    face_files = list(faces_dir.glob("f*.png"))
    if not face_files:
        logger.warning("No face files found, copying source to output")
        await copy_as_placeholder(edited_png, out_png)
        return
    
    # 첫 번째 얼굴 이미지를 소스로 사용 (간단한 구현)
    source_face = face_files[0]
    
    # === FaceFusion 기능 임시 비활성화 ===
    # 복잡한 FaceFusion CLI 처리 대신 입력 이미지를 그대로 출력으로 복사
    logger.info("FaceFusion temporarily disabled - copying input image to output")
    
    # FaceFusion CLI 명령어 (주석 처리)
    # cmd = [
    #     "python", "/home/catch/facefusion/facefusion.py",
    #     "run",
    #     "-s", str(source_face),  # --source
    #     "-t", str(edited_png),   # --target  
    #     "-o", str(out_png),      # --output
    #     "--execution-providers", "cuda",
    #     "--face-detector-model", "yolo_face",
    #     "--face-swapper-model", "inswapper_128"
    # ]
    
    # GPU 동시성 제어를 위한 비동기 락 (향후 FaceFusion 재활성화를 위해 유지)
    async with AsyncFileLock("/tmp/facefusion.lock"):
        try:
            # 간단한 구현: 입력 이미지를 출력으로 복사
            logger.info(f"Copying input image {edited_png} to output {out_png}")
            await copy_as_placeholder(edited_png, out_png)
            logger.info("Face swap completed (FaceFusion disabled - copied input to output)")
            
        except Exception as e:
            logger.error(f"Face swap copy operation failed: {str(e)}")
            raise RuntimeError(f"Face swap failed: {str(e)}")


class AsyncFileLock:
    """비동기 파일 기반 락"""
    _locks = {}  # 락 인스턴스들을 저장하는 클래스 변수
    
    def __init__(self, path: str):
        import asyncio
        self.path = path
        # 같은 파일에 대해서는 같은 락을 사용
        if path not in AsyncFileLock._locks:
            AsyncFileLock._locks[path] = asyncio.Lock()
        self.lock = AsyncFileLock._locks[path]
    
    async def __aenter__(self):
        await self.lock.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()


# 하위 호환성을 위한 기존 FileLock도 유지
class FileLock:
    """파일 기반 락 (동기)"""
    def __init__(self, path: Path): 
        self.path = path
        self.fd = None
        
    def __enter__(self):
        import fcntl, os
        self.fd = os.open(str(self.path), os.O_CREAT|os.O_RDWR, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self
        
    def __exit__(self, *exc):
        import fcntl, os
        try: 
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)


# ---------- 파이프라인 함수들 ----------

async def gpt_only_pipeline(job_id: str, input_url: str, prompt: str, 
                           exif_strip: bool = True, use_face_mask: bool = False, 
                           mask_feather_pixels: int = 12, face_expand_ratio: float = 0.3,
                           set_status_func=None, record_event_func=None):
    """GPT 편집만 수행하는 파이프라인"""
    paths = ensure_tree(job_id)
    logs = paths["base"]/"logs.txt"
    
    logger.info(f"Starting GPT-only pipeline for job_id: {job_id}")
    
    try:
        # 상태 업데이트
        if set_status_func:
            set_status_func(job_id, "editing")
        
        # 1. 입력 이미지 다운로드
        input_png = await download_and_strip(input_url, paths["input"], exif_strip)
        
        # 파라미터 저장
        params = {
            "mode": "gpt_only",
            "input_image_url": input_url,
            "prompt": prompt,
            "exif_strip": exif_strip,
            "use_face_mask": use_face_mask,
            "mask_feather_pixels": mask_feather_pixels,
            "face_expand_ratio": face_expand_ratio
        }
        write_params_and_prompt(paths["base"], params, prompt)
        
        # 2. GPT 이미지 편집
        if record_event_func:
            record_event_func(job_id, "gpt:start")
            
        edited_png = paths["gpt"]/"edited.png"
        await gpt_edit_image(input_png, prompt, edited_png, use_face_mask, 
                            mask_feather_pixels, face_expand_ratio)
        
        if record_event_func:
            record_event_func(job_id, "gpt:done")
        
        # 3. 결과를 final로 복사
        import asyncio
        await asyncio.to_thread(shutil.copy2, edited_png, paths["final"]/"result.png")
        
        # 완료 상태 설정
        if set_status_func:
            set_status_func(job_id, "done")
            
        logger.info(f"GPT-only pipeline completed for job_id: {job_id}")
        
    except Exception as e:
        logger.error(f"GPT-only pipeline failed for {job_id}: {str(e)}", exc_info=True)
        if set_status_func:
            set_status_func(job_id, "failed", error=str(e))
        logs.write_text(f"{datetime.now().isoformat()} ERROR: {e}\n", encoding="utf-8")
        raise


async def face_only_pipeline(job_id: str, input_url: str, faces: List[FaceRef],
                            mapping: Union[str, List[int]] = "similarity", 
                            top1_only: bool = False, threshold: float = SIM_THRESHOLD,
                            exif_strip: bool = True, set_status_func=None, record_event_func=None):
    """FaceFusion만 수행하는 파이프라인"""
    paths = ensure_tree(job_id)
    logs = paths["base"]/"logs.txt"
    
    logger.info(f"Starting face-only pipeline for job_id: {job_id}")
    
    try:
        # 상태 업데이트
        if set_status_func:
            set_status_func(job_id, "faceswap")
        
        # 1. 입력 이미지 다운로드
        input_png = await download_and_strip(input_url, paths["input"], exif_strip)
        
        # 2. 얼굴 이미지들 다운로드
        await download_faces(faces, paths["faces"])
        
        # 파라미터 저장
        mapping_str = mapping if isinstance(mapping, str) else json.dumps(mapping)
        params = {
            "mode": "face_only",
            "input_image_url": input_url,
            "faces": [{"source_url": f.source_url} for f in faces],
            "mapping": mapping_str,
            "top1_only": top1_only,
            "threshold": threshold,
            "exif_strip": exif_strip
        }
        write_params_and_prompt(paths["base"], params)
        
        # 3. FaceFusion 실행 (입력 이미지 직접 사용)
        if record_event_func:
            record_event_func(job_id, "faceswap:start")
            
        result_png = paths["final"]/"result.png"
        await run_facefusion_runner(
            input_png, paths["faces"], result_png,
            mapping=mapping_str, top1_only=top1_only, threshold=threshold
        )
        
        if record_event_func:
            record_event_func(job_id, "faceswap:done")
        
        # 완료 상태 설정
        if set_status_func:
            set_status_func(job_id, "done")
            
        logger.info(f"Face-only pipeline completed for job_id: {job_id}")
        
    except Exception as e:
        logger.error(f"Face-only pipeline failed for {job_id}: {str(e)}", exc_info=True)
        if set_status_func:
            set_status_func(job_id, "failed", error=str(e))
        logs.write_text(f"{datetime.now().isoformat()} ERROR: {e}\n", encoding="utf-8")
        raise


async def full_pipeline(job_id: str, payload: CreateJob, 
                       set_status_func=None, record_event_func=None):
    """전체 파이프라인 (GPT + FaceFusion)"""
    paths = ensure_tree(job_id)
    logs = paths["base"]/"logs.txt"
    
    logger.info(f"Starting full pipeline for job_id: {job_id}")
    
    try:
        # 상태 업데이트
        if set_status_func:
            set_status_func(job_id, "editing")
        
        # 1. 입력 이미지와 얼굴들 다운로드
        input_png = await download_and_strip(payload.input_image_url, paths["input"], payload.exif_strip)
        
        # 얼굴 이미지들 다운로드
        if payload.faces:
            await download_faces(payload.faces, paths["faces"])
        
        # 파라미터 저장
        write_params_and_prompt(paths["base"], payload.model_dump(), payload.prompt)
        
        # 2. GPT 이미지 편집
        if record_event_func:
            record_event_func(job_id, "gpt:start")
            
        edited_png = paths["gpt"]/"edited.png"
        if USE_OPENAI and OPENAI_API_KEY and payload.prompt:
            use_face_mask = getattr(payload, 'use_face_mask', False)
            mask_feather_pixels = getattr(payload, 'mask_feather_pixels', 12)
            face_expand_ratio = getattr(payload, 'face_expand_ratio', 0.3)
            await gpt_edit_image(input_png, payload.prompt, edited_png, 
                               use_face_mask, mask_feather_pixels, face_expand_ratio)
        else:
            await copy_as_placeholder(input_png, edited_png)
            
        if record_event_func:
            record_event_func(job_id, "gpt:done")
            
        if set_status_func:
            set_status_func(job_id, "edited")
        
        # 3. FaceFusion (얼굴이 있는 경우)
        if payload.faces:
            if set_status_func:
                set_status_func(job_id, "faceswap")
                
            result_png = paths["final"]/"result.png"
            mapping = payload.mapping if isinstance(payload.mapping, str) else json.dumps(payload.mapping)
            
            await run_facefusion_runner(
                edited_png, paths["faces"], result_png,
                mapping=mapping, top1_only=payload.top1_only, threshold=payload.threshold
            )
        else:
            # 얼굴이 없으면 GPT 결과를 최종 결과로
            import asyncio
            await asyncio.to_thread(shutil.copy2, edited_png, paths["final"]/"result.png")
        
        # 4. 완료
        if set_status_func:
            set_status_func(job_id, "finalizing")
        if set_status_func:
            set_status_func(job_id, "done")
            
        logger.info(f"Full pipeline completed for job_id: {job_id}")
        
    except Exception as e:
        logger.error(f"Full pipeline failed for {job_id}: {str(e)}", exc_info=True)
        if set_status_func:
            set_status_func(job_id, "failed", error=str(e))
        logs.write_text(f"{datetime.now().isoformat()} ERROR: {e}\n", encoding="utf-8")
        raise
"""
API 테스트 설정 파일
"""

from pathlib import Path

# 서버 설정
SERVER_URL = "http://localhost:8000"
# 또는 프로덕션 서버: "https://image.nearzoom.store"

# 테스트 이미지 디렉토리
TEST_IMAGES_DIR = Path("/home/catch/media/uploads")  # 기존 업로드된 이미지들 사용

# GPT 편집 테스트용 프롬프트들
GPT_TEST_PROMPTS = [
    "make it look like a vintage photograph with sepia tones",
    "add beautiful sunset lighting",
    "make it look like a professional portrait",
    "add snow falling in the background",
    "make it look like a painting in impressionist style"
]

# 얼굴 교체 설정
FACE_SWAP_CONFIG = {
    "mapping": "similarity",  # "similarity", "left_to_right", 또는 [0, 1, 2, 3]
    "threshold": 0.35,
    "top1_only": False
}

# 폴링 설정
POLLING_INTERVAL = 2  # 상태 확인 간격 (초)
MAX_WAIT_TIME = 300   # 최대 대기 시간 (5분)

# 결과 저장 디렉토리
RESULTS_DIR = Path("test_results")

# 테스트 시나리오별 설정
TEST_SCENARIOS = {
    "gpt_basic": {
        "name": "Basic GPT Edit Test",
        "source_image": "cat.jpg",  # 기존 업로드된 이미지 사용
        "prompt": "make this cat look like it's in a magical forest"
    },
    
    "face_swap_basic": {
        "name": "Basic Face Swap Test", 
        "source_image": "20250729_101126_d7e80a4c.jpg",  # 기존 업로드된 이미지
        "face_images": ["cat.jpg"],  # 얼굴로 사용할 이미지
        "mapping": "similarity"
    },
    
    "face_swap_multiple": {
        "name": "Multiple Face Swap Test",
        "source_image": "20250808_130000_21073f79.png",
        "face_images": ["20250729_081341_0ff7cc50.jpg", "cat.jpg"],
        "mapping": "left_to_right"
    }
}

# API 엔드포인트 경로
ENDPOINTS = {
    "health": "/health",
    "upload": "/upload", 
    "gpt_edit": "/jobs/gpt-edit",
    "face_swap": "/jobs/face-swap",
    "job_status": "/jobs/{job_id}",
    "full_pipeline": "/jobs"
}

# 테스트용 샘플 데이터
SAMPLE_REQUESTS = {
    "gpt_edit": {
        "input_image_url": "https://image.nearzoom.store/media/uploads/cat.jpg",
        "prompt": "make it look like a professional studio portrait",
        "exif_strip": True
    },
    
    "face_swap": {
        "input_image_url": "https://image.nearzoom.store/media/uploads/20250729_101126_d7e80a4c.jpg",
        "faces": [
            {"source_url": "https://image.nearzoom.store/media/uploads/cat.jpg"}
        ],
        "mapping": "similarity",
        "top1_only": False,
        "threshold": 0.35,
        "exif_strip": True
    },
    
    "full_pipeline": {
        "input_image_url": "https://image.nearzoom.store/media/uploads/cat.jpg",
        "prompt": "make it look vintage with warm lighting",
        "faces": [
            {"source_url": "https://image.nearzoom.store/media/uploads/20250729_081341_0ff7cc50.jpg"}
        ],
        "mapping": "similarity",
        "top1_only": False,
        "threshold": 0.35,
        "exif_strip": True
    }
}

# 에러 메시지 및 상태 코드
EXPECTED_RESPONSES = {
    "upload_success": 200,
    "job_created": 201,
    "job_found": 200,
    "job_not_found": 404,
    "invalid_request": 400,
    "server_error": 500
}

# 로그 설정
LOGGING_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "file": "test_results/test_log.txt"
}
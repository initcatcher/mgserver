#!/bin/bash

# FastAPI 사진 업로드 서버 시작 스크립트

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 스크립트 디렉토리로 이동
cd "$(dirname "$0")"

echo -e "${GREEN}AI 이미지 처리 서버 시작 중...${NC}"

# Conda 환경 활성화
echo -e "${YELLOW}Conda 환경 활성화 중...${NC}"
source /home/catch/miniconda3/etc/profile.d/conda.sh
conda activate facefusion

# 환경 확인
if [[ "$CONDA_DEFAULT_ENV" != "facefusion" ]]; then
    echo -e "${RED}Error: facefusion 환경 활성화 실패${NC}"
    exit 1
fi

echo -e "${GREEN}Conda 환경 활성화 완료: $CONDA_DEFAULT_ENV${NC}"

# 의존성 설치 확인
echo -e "${YELLOW}의존성 설치 확인 중...${NC}"
pip install -r requirements.txt

# 서버 시작
echo -e "${GREEN}AI 이미지 처리 서버 시작 (포트: 8000)${NC}"
echo -e "${YELLOW}서버 중지: Ctrl+C${NC}"
echo -e "${YELLOW}API 문서: http://localhost/docs${NC}"
echo -e "${YELLOW}작업 생성: POST /jobs${NC}"
echo -e "${YELLOW}작업 조회: GET /jobs/{job_id}${NC}"

python main_jobs.py
# FastAPI 사진 업로드 서버

Nginx와 연동된 FastAPI 사진 업로드 서버입니다.

## 설치 및 실행

### 1. 서버 시작
```bash
cd /home/catch/server
./start_server.sh
```

### 2. 수동 실행 (개발용)
```bash
# conda 환경 활성화
conda activate facefusion

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
python main.py
```

## API 엔드포인트

### 서버 상태 확인
- `GET /` - 서버 정보
- `GET /health` - 헬스 체크

### 파일 업로드
- `POST /upload` - 사진 업로드
  - Form data: `file` (이미지 파일)
  - 지원 형식: jpg, jpeg, png, gif, webp, bmp
  - 최대 크기: 50MB

### 업로드된 파일 목록
- `GET /uploads` - 업로드된 파일 목록 조회

## 사용 방법

### curl로 파일 업로드
```bash
curl -X POST "http://localhost/upload" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@/path/to/your/image.jpg"
```

### 웹 브라우저에서 테스트
1. http://localhost/docs 접속
2. `/upload` 엔드포인트 선택
3. "Try it out" 클릭
4. 파일 선택 후 "Execute"

## 파일 경로

- **업로드 저장소**: `/media/uploads/`
- **접근 URL**: `http://localhost/media/uploads/파일명`
- **Nginx 프록시**: `http://localhost` → `http://127.0.0.1:8000`

## 보안 설정

- 이미지 파일만 업로드 허용
- 파일 크기 제한 (50MB)
- 파일명 중복 방지 (UUID + 타임스탬프)
- Nginx Rate limiting 적용

## 로그

- FastAPI 로그: 터미널 출력
- Nginx 로그: `/var/log/nginx/media_access.log`, `/var/log/nginx/media_error.log`
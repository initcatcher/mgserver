# AI 이미지 처리 서버 테스트 가이드

## 📋 개요

이 테스트 스크립트들은 AI 이미지 처리 서버의 GPT-edit와 Face-swap 기능을 자동으로 테스트합니다.

## 🚀 빠른 시작

### 1. 서버 실행
```bash
# main_jobs.py 서버가 실행되어 있는지 확인
cd /home/catch/server
python main_jobs.py
```

### 2. 간단한 테스트 실행
```bash
# 간편 테스트 스크립트 실행
python run_tests.py
```

### 3. 상세 테스트 실행  
```bash
# 모든 테스트 실행
python test_scenarios.py --test all --save-results

# GPT 편집만 테스트
python test_scenarios.py --test gpt

# 얼굴 교체만 테스트
python test_scenarios.py --test face

# 서버 상태만 확인
python test_scenarios.py --test health
```

## 📁 테스트 파일 구조

```
/home/catch/server/
├── test_scenarios.py    # 상세 테스트 스크립트
├── test_config.py       # 테스트 설정
├── run_tests.py         # 간편 테스트 실행
├── TEST_README.md       # 이 파일
└── results/            # 테스트 결과 이미지 (생성됨)
```

## 🎯 테스트 시나리오

### GPT-Edit 테스트
1. **기존 이미지 사용**: `/media/uploads/cat.jpg`
2. **프롬프트 적용**: "make this cat look like it's in a magical enchanted forest"
3. **작업 생성**: `POST /jobs/gpt-edit`
4. **상태 모니터링**: 완료까지 실시간 추적
5. **결과 확인**: 처리된 이미지 URL 출력

### Face-Swap 테스트
1. **원본 이미지**: `/media/uploads/20250729_101126_d7e80a4c.jpg`
2. **얼굴 이미지**: `/media/uploads/cat.jpg`
3. **작업 생성**: `POST /jobs/face-swap`
4. **상태 모니터링**: 완료까지 실시간 추적
5. **결과 확인**: 얼굴이 교체된 이미지 URL 출력

## 📊 예상 출력

```
🚀 AI Image Processing Server Tests
Server: http://localhost:8000

==================================================
 Server Health Check
==================================================
✅ Server is running
✅ Supported modes: gpt_only, face_only, both

==================================================
 GPT Image Edit Test
==================================================
📋 Using image: https://image.nearzoom.store/media/uploads/cat.jpg
📋 Prompt: make this cat look like it's in a magical enchanted forest with glowing mushrooms
✅ GPT job created: 20250811-123456-abc123
⏳ Waiting for job completion...
Status: editing (25%)
Status: edited (50%)
Status: done (100%)
✅ Job completed!
✅ Result: https://image.nearzoom.store/media/jobs/20250811-123456-abc123/final/result.png

==================================================
 Face Swap Test
==================================================
📋 Source image: https://image.nearzoom.store/media/uploads/20250729_101126_d7e80a4c.jpg
📋 Face image: https://image.nearzoom.store/media/uploads/cat.jpg
✅ Face-swap job created: 20250811-123457-def456
⏳ Waiting for job completion...
Status: faceswap (75%)
Status: done (100%)
✅ Job completed!
✅ Result: https://image.nearzoom.store/media/jobs/20250811-123457-def456/final/result.png

==================================================
 Test Results Summary
==================================================
✅ GPT Edit Test: PASSED
✅ Face Swap Test: PASSED

🎉 All tests passed!
```

## ⚙️ 설정 변경

### 서버 URL 변경
```python
# test_config.py 또는 run_tests.py에서
SERVER_URL = "https://image.nearzoom.store"  # 프로덕션 서버
```

### 다른 이미지 사용
```python
# test_config.py에서 TEST_SCENARIOS 수정
"source_image": "your_image.jpg"  # 업로드된 이미지 이름
```

### GPT 프롬프트 변경
```python
# test_config.py에서 GPT_TEST_PROMPTS 수정
GPT_TEST_PROMPTS = [
    "your custom prompt here",
    "another creative prompt"
]
```

## 🔧 트러블슈팅

### 서버 연결 실패
```bash
# 서버가 실행 중인지 확인
ps aux | grep main_jobs.py

# 포트 확인
netstat -tlnp | grep :8000
```

### 이미지 없음 에러
```bash
# 업로드된 이미지 확인
ls -la /home/catch/media/uploads/

# 새 이미지 업로드
curl -X POST http://localhost:8000/upload -F "file=@your_image.jpg"
```

### 작업 실패
- OpenAI API 키가 설정되어 있는지 확인 (GPT-edit용)
- FaceFusion이 제대로 설치되어 있는지 확인
- 서버 로그 확인: `tail -f /home/catch/media/server.log`

## 📝 의존성

테스트 실행에 필요한 패키지:
```bash
pip install requests
```

## 🎓 사용 예시

### 커스텀 테스트 작성
```python
from test_scenarios import TestRunner

runner = TestRunner("http://localhost:8000")

# 커스텀 GPT 테스트
success = runner.test_gpt_edit(
    test_image="my_image.jpg",
    prompt="make it look like a Van Gogh painting",
    save_result=True
)

# 커스텀 얼굴 교체 테스트  
success = runner.test_face_swap(
    source_image="group_photo.jpg",
    face_images=["face1.jpg", "face2.jpg"],
    mapping="left_to_right"
)
```

## 📈 결과 분석

테스트 완료 후 다음을 확인할 수 있습니다:
- 각 작업의 처리 시간
- 생성된 이미지 품질
- API 응답 속도
- 에러 발생 여부

결과 이미지는 브라우저에서 직접 확인하거나 `--save-results` 옵션으로 로컬에 다운로드할 수 있습니다.
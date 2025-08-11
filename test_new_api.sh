#!/bin/bash

# 새로운 API 테스트 스크립트

API_URL="http://localhost:8000"

echo "=== 새로운 POST /jobs API 테스트 ==="
echo ""

# 1. Color 타입 테스트
echo "1. Color 타입 요청:"
curl -X POST "${API_URL}/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://image.nearzoom.store/media/uploads/me_20250811_064840_773c6258.jpg",
    "person_ids": ["person_001", "person_002", "person_003"],
    "processing_options": {
      "type": "color",
      "color": "warm autumn"
    }
  }' | python -m json.tool

echo ""
echo "---"
echo ""

# 2. Prompt 타입 테스트
echo "2. Prompt 타입 요청:"
curl -X POST "${API_URL}/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://image.nearzoom.store/media/uploads/me_20250811_064840_773c6258.jpg",
    "person_ids": ["person_001"],
    "processing_options": {
      "type": "prompt",
      "prompt": "Change background to Korean traditional market, preserve all faces and people, vibrant colors"
    }
  }' | python -m json.tool

echo ""
echo "---"
echo ""

# 3. 에러 케이스 테스트 (person_ids 없음)
echo "3. 에러 테스트 - person_ids 없음:"
curl -X POST "${API_URL}/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://image.nearzoom.store/media/uploads/test.jpg",
    "person_ids": [],
    "processing_options": {
      "type": "color",
      "color": "blue"
    }
  }' | python -m json.tool

echo ""
echo "---"
echo ""

# 4. 에러 케이스 테스트 (prompt 없음)
echo "4. 에러 테스트 - prompt 없음:"
curl -X POST "${API_URL}/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://image.nearzoom.store/media/uploads/test.jpg",
    "person_ids": ["person_001"],
    "processing_options": {
      "type": "prompt"
    }
  }' | python -m json.tool

echo ""
echo "=== 테스트 완료 ==="
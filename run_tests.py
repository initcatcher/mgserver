#!/usr/bin/env python3
"""
간편한 테스트 실행 스크립트
기존 업로드된 이미지들을 사용하여 GPT-edit와 Face-swap 테스트
"""

import requests
import time
import json
from pathlib import Path

# 설정
SERVER_URL = "http://localhost:8000"
BASE_IMAGE_URL = "https://image.nearzoom.store/media/uploads"

def print_step(message, status="info"):
    icons = {"success": "✅", "error": "❌", "info": "📋", "waiting": "⏳"}
    print(f"{icons.get(status, '📋')} {message}")

def wait_for_job(job_id):
    """작업 완료까지 대기"""
    print_step("Waiting for job completion...", "waiting")
    
    while True:
        try:
            response = requests.get(f"{SERVER_URL}/jobs/{job_id}")
            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                progress = data.get('progress', 0)
                
                print(f"Status: {status} ({progress}%)")
                
                if status == "done":
                    print_step("Job completed!", "success")
                    return data
                elif status == "failed":
                    print_step(f"Job failed: {data.get('error', 'Unknown error')}", "error")
                    return None
                    
        except Exception as e:
            print_step(f"Status check error: {e}", "error")
            
        time.sleep(3)

def test_gpt_edit():
    """GPT 편집 테스트"""
    print("\n" + "="*50)
    print(" GPT Image Edit Test")
    print("="*50)
    
    # 기존 업로드된 이미지 사용
    image_url = f"{BASE_IMAGE_URL}/cat.jpg"
    prompt = "make this cat look like it's in a magical enchanted forest with glowing mushrooms"
    
    print_step(f"Using image: {image_url}")
    print_step(f"Prompt: {prompt}")
    
    # GPT 편집 작업 생성
    payload = {
        "input_image_url": image_url,
        "prompt": prompt,
        "exif_strip": True
    }
    
    try:
        response = requests.post(f"{SERVER_URL}/jobs/gpt-edit", json=payload)
        
        if response.status_code == 201:
            data = response.json()
            job_id = data['job_id']
            print_step(f"GPT job created: {job_id}", "success")
            
            # 작업 완료 대기
            result = wait_for_job(job_id)
            if result:
                final_url = result.get('artifacts', {}).get('final')
                if final_url:
                    print_step(f"Result: {final_url}", "success")
                    return True
        else:
            print_step(f"Job creation failed: {response.status_code} - {response.text}", "error")
            
    except Exception as e:
        print_step(f"GPT test error: {e}", "error")
    
    return False

def test_face_swap():
    """얼굴 교체 테스트"""
    print("\n" + "="*50)
    print(" Face Swap Test")
    print("="*50)
    
    # 기존 업로드된 이미지들 사용
    source_url = f"{BASE_IMAGE_URL}/20250729_101126_d7e80a4c.jpg"
    face_url = f"{BASE_IMAGE_URL}/cat.jpg"
    
    print_step(f"Source image: {source_url}")
    print_step(f"Face image: {face_url}")
    
    # 얼굴 교체 작업 생성
    payload = {
        "input_image_url": source_url,
        "faces": [
            {"source_url": face_url}
        ],
        "mapping": "similarity",
        "top1_only": False,
        "threshold": 0.35,
        "exif_strip": True
    }
    
    try:
        response = requests.post(f"{SERVER_URL}/jobs/face-swap", json=payload)
        
        if response.status_code == 201:
            data = response.json()
            job_id = data['job_id']
            print_step(f"Face-swap job created: {job_id}", "success")
            
            # 작업 완료 대기
            result = wait_for_job(job_id)
            if result:
                final_url = result.get('artifacts', {}).get('final')
                if final_url:
                    print_step(f"Result: {final_url}", "success")
                    return True
        else:
            print_step(f"Job creation failed: {response.status_code} - {response.text}", "error")
            
    except Exception as e:
        print_step(f"Face swap test error: {e}", "error")
    
    return False

def test_server_health():
    """서버 상태 확인"""
    print("\n" + "="*50)
    print(" Server Health Check")
    print("="*50)
    
    try:
        # 기본 상태 확인
        response = requests.get(f"{SERVER_URL}/")
        if response.status_code == 200:
            print_step("Server is running", "success")
        else:
            print_step("Server not responding", "error")
            return False
        
        # 헬스 체크
        response = requests.get(f"{SERVER_URL}/health")
        if response.status_code == 200:
            data = response.json()
            modes = data.get('mode_support', [])
            print_step(f"Supported modes: {', '.join(modes)}", "success")
            return True
        
    except Exception as e:
        print_step(f"Health check failed: {e}", "error")
        return False

def main():
    """메인 테스트 실행"""
    print("🚀 AI Image Processing Server Tests")
    print(f"Server: {SERVER_URL}")
    
    # 1. 서버 상태 확인
    if not test_server_health():
        print("❌ Server not available. Please check if main_jobs.py is running.")
        return
    
    # 2. GPT 편집 테스트
    gpt_success = test_gpt_edit()
    
    # 3. 얼굴 교체 테스트  
    face_success = test_face_swap()
    
    # 결과 요약
    print("\n" + "="*50)
    print(" Test Results Summary")
    print("="*50)
    
    print_step(f"GPT Edit Test: {'PASSED' if gpt_success else 'FAILED'}", 
               "success" if gpt_success else "error")
    print_step(f"Face Swap Test: {'PASSED' if face_success else 'FAILED'}", 
               "success" if face_success else "error")
    
    if gpt_success and face_success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Some tests failed. Check the logs above.")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
AI 이미지 처리 서버 테스트 시나리오
- GPT 이미지 편집 테스트
- FaceFusion 얼굴 교체 테스트
"""

import asyncio
import time
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import argparse

from test_config import (
    SERVER_URL, 
    TEST_IMAGES_DIR,
    GPT_TEST_PROMPTS,
    FACE_SWAP_CONFIG,
    POLLING_INTERVAL,
    MAX_WAIT_TIME
)


class TestRunner:
    """API 테스트 실행기"""
    
    def __init__(self, base_url: str = SERVER_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
    def print_header(self, title: str):
        """테스트 섹션 헤더 출력"""
        print(f"\n{'='*50}")
        print(f" {title}")
        print(f"{'='*50}")
        
    def print_step(self, step: str, status: str = ""):
        """테스트 단계 출력"""
        if status == "success":
            print(f"✅ {step}")
        elif status == "error":
            print(f"❌ {step}")
        elif status == "waiting":
            print(f"⏳ {step}")
        else:
            print(f"📋 {step}")
    
    def upload_image(self, image_path: Path) -> Optional[str]:
        """이미지 업로드 후 URL 반환"""
        try:
            if not image_path.exists():
                self.print_step(f"Image not found: {image_path}", "error")
                return None
                
            with open(image_path, 'rb') as f:
                files = {'file': (image_path.name, f, 'image/jpeg')}
                response = self.session.post(f"{self.base_url}/upload", files=files)
                
            if response.status_code == 200:
                data = response.json()
                file_url = data['data']['file_url']
                self.print_step(f"Image uploaded: {file_url}", "success")
                return file_url
            else:
                self.print_step(f"Upload failed: {response.status_code} - {response.text}", "error")
                return None
                
        except Exception as e:
            self.print_step(f"Upload error: {str(e)}", "error")
            return None
    
    def create_gpt_job(self, input_url: str, prompt: str) -> Optional[str]:
        """GPT 편집 작업 생성"""
        try:
            payload = {
                "input_image_url": input_url,
                "prompt": prompt,
                "exif_strip": True
            }
            
            response = self.session.post(
                f"{self.base_url}/jobs/gpt-edit",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 201:
                data = response.json()
                job_id = data['job_id']
                self.print_step(f"GPT job created: {job_id}", "success")
                return job_id
            else:
                self.print_step(f"GPT job creation failed: {response.status_code} - {response.text}", "error")
                return None
                
        except Exception as e:
            self.print_step(f"GPT job error: {str(e)}", "error")
            return None
    
    def create_face_swap_job(self, input_url: str, face_urls: list, 
                           mapping: str = "similarity", threshold: float = 0.35) -> Optional[str]:
        """얼굴 교체 작업 생성"""
        try:
            faces = [{"source_url": url} for url in face_urls]
            payload = {
                "input_image_url": input_url,
                "faces": faces,
                "mapping": mapping,
                "top1_only": False,
                "threshold": threshold,
                "exif_strip": True
            }
            
            response = self.session.post(
                f"{self.base_url}/jobs/face-swap",
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 201:
                data = response.json()
                job_id = data['job_id']
                self.print_step(f"Face-swap job created: {job_id}", "success")
                return job_id
            else:
                self.print_step(f"Face-swap job creation failed: {response.status_code} - {response.text}", "error")
                return None
                
        except Exception as e:
            self.print_step(f"Face-swap job error: {str(e)}", "error")
            return None
    
    def wait_for_job_completion(self, job_id: str) -> Optional[Dict[Any, Any]]:
        """작업 완료까지 대기"""
        start_time = time.time()
        last_status = ""
        
        while time.time() - start_time < MAX_WAIT_TIME:
            try:
                response = self.session.get(f"{self.base_url}/jobs/{job_id}")
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', 'unknown')
                    progress = data.get('progress', 0)
                    
                    if status != last_status:
                        self.print_step(f"Status: {status} ({progress}%)", "waiting")
                        last_status = status
                    
                    if status == "done":
                        self.print_step("Job completed!", "success")
                        return data
                    elif status == "failed":
                        error = data.get('error', 'Unknown error')
                        self.print_step(f"Job failed: {error}", "error")
                        return data
                        
                else:
                    self.print_step(f"Status check failed: {response.status_code}", "error")
                    
            except Exception as e:
                self.print_step(f"Status check error: {str(e)}", "error")
            
            time.sleep(POLLING_INTERVAL)
        
        self.print_step(f"Job timeout after {MAX_WAIT_TIME} seconds", "error")
        return None
    
    def download_result(self, result_url: str, save_path: Path):
        """결과 이미지 다운로드"""
        try:
            response = self.session.get(result_url)
            if response.status_code == 200:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(response.content)
                self.print_step(f"Result saved: {save_path}", "success")
                return True
            else:
                self.print_step(f"Download failed: {response.status_code}", "error")
                return False
        except Exception as e:
            self.print_step(f"Download error: {str(e)}", "error")
            return False
    
    def test_gpt_edit(self, test_image: str, prompt: str, save_result: bool = True):
        """GPT 이미지 편집 테스트"""
        self.print_header("GPT Image Editing Test")
        
        # 1. 이미지 업로드
        image_path = TEST_IMAGES_DIR / test_image
        input_url = self.upload_image(image_path)
        if not input_url:
            return False
        
        # 2. GPT 편집 작업 생성
        job_id = self.create_gpt_job(input_url, prompt)
        if not job_id:
            return False
        
        # 3. 작업 완료 대기
        result = self.wait_for_job_completion(job_id)
        if not result or result.get('status') != 'done':
            return False
        
        # 4. 결과 출력
        artifacts = result.get('artifacts', {})
        final_url = artifacts.get('final')
        
        if final_url:
            self.print_step(f"Result URL: {final_url}", "success")
            
            if save_result:
                save_path = Path(f"results/gpt_edit_{job_id}_result.png")
                self.download_result(final_url, save_path)
        
        return True
    
    def test_face_swap(self, source_image: str, face_images: list, 
                      mapping: str = "similarity", save_result: bool = True):
        """얼굴 교체 테스트"""
        self.print_header("Face Swap Test")
        
        # 1. 원본 이미지 업로드
        source_path = TEST_IMAGES_DIR / source_image
        source_url = self.upload_image(source_path)
        if not source_url:
            return False
        
        # 2. 얼굴 이미지들 업로드
        face_urls = []
        for face_image in face_images:
            face_path = TEST_IMAGES_DIR / face_image
            face_url = self.upload_image(face_path)
            if face_url:
                face_urls.append(face_url)
            else:
                self.print_step(f"Failed to upload face image: {face_image}", "error")
        
        if not face_urls:
            self.print_step("No face images uploaded", "error")
            return False
        
        # 3. 얼굴 교체 작업 생성
        job_id = self.create_face_swap_job(source_url, face_urls, mapping)
        if not job_id:
            return False
        
        # 4. 작업 완료 대기
        result = self.wait_for_job_completion(job_id)
        if not result or result.get('status') != 'done':
            return False
        
        # 5. 결과 출력
        artifacts = result.get('artifacts', {})
        final_url = artifacts.get('final')
        
        if final_url:
            self.print_step(f"Result URL: {final_url}", "success")
            
            if save_result:
                save_path = Path(f"results/face_swap_{job_id}_result.png")
                self.download_result(final_url, save_path)
        
        return True
    
    def test_server_health(self):
        """서버 상태 확인"""
        self.print_header("Server Health Check")
        
        try:
            # 기본 상태 확인
            response = self.session.get(f"{self.base_url}/")
            if response.status_code == 200:
                self.print_step("Server is running", "success")
            else:
                self.print_step("Server not responding", "error")
                return False
            
            # 헬스 체크
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                modes = data.get('mode_support', [])
                self.print_step(f"Supported modes: {', '.join(modes)}", "success")
            
            return True
            
        except Exception as e:
            self.print_step(f"Health check error: {str(e)}", "error")
            return False


def main():
    """메인 테스트 실행"""
    parser = argparse.ArgumentParser(description='AI Image Processing Server Test')
    parser.add_argument('--test', choices=['health', 'gpt', 'face', 'all'], 
                       default='all', help='Test to run')
    parser.add_argument('--server', default=SERVER_URL, help='Server URL')
    parser.add_argument('--save-results', action='store_true', 
                       help='Save result images locally')
    
    args = parser.parse_args()
    
    # 테스트 실행
    runner = TestRunner(args.server)
    
    print(f"🚀 Starting tests against: {args.server}")
    
    if args.test in ['health', 'all']:
        if not runner.test_server_health():
            print("❌ Server health check failed. Exiting.")
            return
    
    if args.test in ['gpt', 'all']:
        # GPT 편집 테스트
        for prompt in GPT_TEST_PROMPTS:
            success = runner.test_gpt_edit(
                test_image="test_source.jpg",  # 테스트용 이미지
                prompt=prompt,
                save_result=args.save_results
            )
            if not success:
                print(f"❌ GPT test failed with prompt: {prompt}")
    
    if args.test in ['face', 'all']:
        # 얼굴 교체 테스트
        success = runner.test_face_swap(
            source_image="test_source.jpg",
            face_images=["test_face1.jpg", "test_face2.jpg"],
            mapping="similarity",
            save_result=args.save_results
        )
        if not success:
            print("❌ Face swap test failed")
    
    print("\n🎉 Tests completed!")


if __name__ == "__main__":
    main()
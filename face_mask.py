"""
얼굴 마스크 생성 모듈
MediaPipe를 사용한 얼굴 감지 및 PIL을 사용한 마스크 생성
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import mediapipe as mp
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class FaceMaskGenerator:
    """얼굴 영역 보존을 위한 마스크 생성기"""
    
    def __init__(self):
        self.mp_face_detection = mp.solutions.face_detection
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=0.5
        )
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
    
    def create_face_mask(self, image_path: Path, feather_pixels: int = 12, 
                        expand_ratio: float = 0.3) -> Optional[Path]:
        """
        얼굴과 머리 영역을 보존하는 마스크 생성
        
        Args:
            image_path: 입력 이미지 경로
            feather_pixels: 경계 부드럽게 처리할 픽셀 수
            expand_ratio: 얼굴 영역 확장 비율 (머리카락 포함)
            
        Returns:
            마스크 이미지 경로 (PNG with alpha channel)
        """
        try:
            # 이미지 로드
            pil_image = Image.open(image_path).convert('RGB')
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            height, width = cv_image.shape[:2]
            
            # 얼굴 감지
            face_landmarks = self._detect_face_landmarks(cv_image)
            if not face_landmarks:
                logger.warning("No face detected, creating empty mask")
                return self._create_empty_mask(pil_image.size, image_path)
            
            # 얼굴 윤곽 마스크 생성
            face_mask = self._create_face_contour_mask(
                face_landmarks, (width, height), expand_ratio
            )
            
            # PIL Image로 변환하고 경계 부드럽게 처리
            mask_pil = Image.fromarray(face_mask).convert('L')
            
            # Feather 효과 적용 (경계 부드럽게)
            if feather_pixels > 0:
                mask_pil = mask_pil.filter(ImageFilter.GaussianBlur(radius=feather_pixels//3))
            
            # RGBA 형식으로 변환하여 알파 채널 생성
            mask_rgba = Image.new('RGBA', mask_pil.size, (0, 0, 0, 0))
            mask_rgba.putalpha(mask_pil)
            
            # 마스크 파일 저장
            mask_path = image_path.parent / f"{image_path.stem}_face_mask.png"
            mask_rgba.save(mask_path, 'PNG')
            
            logger.info(f"Face mask created: {mask_path}")
            return mask_path
            
        except Exception as e:
            logger.error(f"Failed to create face mask: {str(e)}")
            return None
    
    def _detect_face_landmarks(self, cv_image: np.ndarray) -> Optional[list]:
        """MediaPipe를 사용한 얼굴 랜드마크 감지"""
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_image)
        
        if results.multi_face_landmarks:
            return results.multi_face_landmarks[0].landmark
        return None
    
    def _create_face_contour_mask(self, landmarks: list, image_size: Tuple[int, int], 
                                 expand_ratio: float) -> np.ndarray:
        """얼굴 윤곽을 기반으로 마스크 생성"""
        width, height = image_size
        
        # 얼굴 윤곽 포인트 (MediaPipe Face Mesh 인덱스)
        # 얼굴 경계, 이마, 턱선 포함
        face_oval_indices = [
            10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
            397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
            172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109
        ]
        
        # 이마 영역 추가 (머리카락 포함을 위해)
        forehead_indices = [9, 10, 151, 337, 299, 333, 298, 301]
        
        # 모든 인덱스 결합
        all_indices = face_oval_indices + forehead_indices
        
        # 좌표 추출 및 정규화
        points = []
        for idx in all_indices:
            if idx < len(landmarks):
                x = int(landmarks[idx].x * width)
                y = int(landmarks[idx].y * height)
                points.append([x, y])
        
        if not points:
            # 기본 타원 마스크 생성
            return self._create_default_oval_mask(image_size)
        
        # Convex Hull로 얼굴 영역 생성
        points = np.array(points)
        hull = cv2.convexHull(points)
        
        # 영역 확장 (머리카락 영역 포함)
        if expand_ratio > 0:
            center = np.mean(hull, axis=0)
            expanded_hull = center + (hull - center) * (1 + expand_ratio)
            hull = expanded_hull.astype(np.int32)
        
        # 마스크 생성 (255=보존 영역, 0=편집 영역)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [hull], 255)
        
        return mask
    
    def _create_default_oval_mask(self, image_size: Tuple[int, int]) -> np.ndarray:
        """기본 타원 마스크 생성 (얼굴 감지 실패 시)"""
        width, height = image_size
        mask = np.zeros((height, width), dtype=np.uint8)
        
        # 중앙에 타원 생성
        center = (width // 2, height // 2)
        axes = (width // 3, height // 2)  # 세로로 긴 타원
        cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
        
        return mask
    
    def _create_empty_mask(self, size: Tuple[int, int], image_path: Path) -> Path:
        """빈 마스크 생성 (전체 이미지 편집 허용)"""
        mask = Image.new('RGBA', size, (0, 0, 0, 0))  # 완전 투명
        mask_path = image_path.parent / f"{image_path.stem}_face_mask.png"
        mask.save(mask_path, 'PNG')
        return mask_path


async def create_face_preservation_mask(image_path: Path, feather_pixels: int = 12, 
                                       expand_ratio: float = 0.3) -> Optional[Path]:
    """
    비동기 얼굴 보존 마스크 생성 함수
    
    Args:
        image_path: 입력 이미지 경로
        feather_pixels: 경계 부드럽게 처리할 픽셀 수
        expand_ratio: 얼굴 영역 확장 비율
        
    Returns:
        마스크 이미지 경로
    """
    import asyncio
    
    def _create_mask_sync():
        generator = FaceMaskGenerator()
        return generator.create_face_mask(image_path, feather_pixels, expand_ratio)
    
    return await asyncio.to_thread(_create_mask_sync)
"""
Frame processing service
Handles creating photo album layouts from multiple images
"""

import os
import logging
from pathlib import Path
from typing import List
from PIL import Image

logger = logging.getLogger(__name__)

class FrameProcessor:
    def __init__(self):
        self.media_root = Path("/home/catch/media")
        self.jobs_dir = self.media_root / "jobs"
    
    def create_photo_album(self, 
                          image_paths: List[str], 
                          background_color_hex: str, 
                          output_path: str) -> str:
        """
        Combine 1-4 images into a photo album style layout.
        
        Args:
            image_paths: List of image file paths (1-4 images)
            background_color_hex: Hex color string (e.g., "#FF80FF")
            output_path: Output file path
        
        Returns:
            str: Generated image file path
        """
        
        if not (1 <= len(image_paths) <= 4):
            raise ValueError(f"Expected 1-4 images, got {len(image_paths)}")
        
        # Validate all image files exist
        for path in image_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Image file not found: {path}")
        
        # Load images
        images = []
        for path in image_paths:
            try:
                img = Image.open(path)
                images.append(img)
            except Exception as e:
                raise ValueError(f"Failed to load image {path}: {str(e)}")
        
        # Image and layout settings
        img_width, img_height = 400, 400
        margin = 27  # Spacing between images
        outer_margin = 27  # Outer padding
        
        # Calculate canvas dimensions based on number of images
        canvas_width = img_width + (outer_margin * 2)
        canvas_height = (img_height * len(images)) + (margin * (len(images) - 1)) + (outer_margin * 2)
        
        # Convert hex color to RGB
        bg_color = self._hex_to_rgb(background_color_hex)
        
        # Create canvas
        canvas = Image.new('RGB', (canvas_width, canvas_height), bg_color)
        
        # Calculate positions for each image
        positions = []
        for i in range(len(images)):
            y_pos = outer_margin + (i * (img_height + margin))
            positions.append((outer_margin, y_pos))
        
        # Paste images onto canvas
        for img, pos in zip(images, positions):
            try:
                # Resize image to fit
                resized_img = img.resize((img_width, img_height), Image.Resampling.LANCZOS)
                canvas.paste(resized_img, pos)
            except Exception as e:
                logger.error(f"Failed to paste image at position {pos}: {str(e)}")
                raise
        
        # Save the result
        try:
            canvas.save(output_path, 'JPEG', quality=95)
            logger.info(f"Frame image saved successfully: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to save frame image: {str(e)}")
            raise
    
    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple"""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Validate hex color format
        if len(hex_color) != 6:
            logger.warning(f"Invalid hex color format: {hex_color}, using white as default")
            return (255, 255, 255)
        
        try:
            # Convert hex to RGB
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16) 
            b = int(hex_color[4:6], 16)
            return (r, g, b)
        except ValueError:
            logger.warning(f"Invalid hex color: {hex_color}, using white as default")
            return (255, 255, 255)
    
    def process_frame_job(self, 
                         job_id: str, 
                         image_paths: List[str], 
                         frame_color: str) -> str:
        """
        Process frame job for given images
        
        Args:
            job_id: Job identifier
            image_paths: List of local image file paths
            frame_color: Background color in hex format
            
        Returns:
            str: Path to generated frame image
        """
        
        # Setup job directory
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Output path for frame result
        output_path = job_dir / "frame_result.jpg"
        
        logger.info(f"Processing frame job {job_id} with {len(image_paths)} images")
        logger.info(f"Frame color: {frame_color}, Output: {output_path}")
        
        try:
            # Create photo album
            result_path = self.create_photo_album(
                image_paths=image_paths,
                background_color_hex=frame_color,
                output_path=str(output_path)
            )
            
            logger.info(f"Frame job {job_id} completed successfully")
            return result_path
            
        except Exception as e:
            logger.error(f"Frame processing failed for job {job_id}: {str(e)}")
            raise

# Singleton instance
frame_processor = FrameProcessor()
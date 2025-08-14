from PIL import Image
import os
from typing import List

def create_photo_album(image_paths: List[str], background_color: List[int], output_path: str = "group_final.png") -> str:
    """
    Combine 4 images into a photo album style layout.
    
    Args:
        image_paths: List of image file paths (exactly 4 required)
        background_color: RGB color list [R, G, B] (0-255)
        output_path: Output file path (default: "group_final.png")
    
    Returns:
        str: Generated image file path
    """
    
    if len(image_paths) != 4:
        raise ValueError("Exactly 4 image paths are required.")
    
    for path in image_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image file not found: {path}")
    
    images = []
    for path in image_paths:
        img = Image.open(path)
        images.append(img)
    
    img_width, img_height = 300, 300
    
    margin = 20  # Spacing between images
    outer_margin = 20  # Outer padding
    
    canvas_width = img_width + (outer_margin * 2)
    canvas_height = (img_height * 4) + (margin * 3) + (outer_margin * 2)
    
    bg_color = tuple(background_color) if len(background_color) == 3 else (255, 255, 255)
    canvas = Image.new('RGB', (canvas_width, canvas_height), bg_color)
    
    positions = [
        (outer_margin, outer_margin),  # Top
        (outer_margin, outer_margin + img_height + margin),  # Second
        (outer_margin, outer_margin + (img_height + margin) * 2),  # Third
        (outer_margin, outer_margin + (img_height + margin) * 3)  # Bottom
    ]
    
    for img, pos in zip(images, positions):
        resized_img = img.resize((img_width, img_height), Image.Resampling.LANCZOS)
        canvas.paste(resized_img, pos)
    
    canvas.save(output_path, 'PNG', quality=95)
    
    return output_path


def main():
    """Test function"""
    image_paths = [
        "booth-test/mvp_result1.jpg",
        "booth-test/mvp_result2.jpg", 
        "booth-test/mvp_result3.jpg",
        "booth-test/mvp_result4.jpg"
    ]
    
    background_color = [255, 128, 255]  # White background
    
    try:
        result_path = create_photo_album(image_paths, background_color, "group_final.png")
        print(f"Photo album created successfully: {result_path}")
    except Exception as e:
        print(f"Error occurred: {e}")


if __name__ == "__main__":
    main()
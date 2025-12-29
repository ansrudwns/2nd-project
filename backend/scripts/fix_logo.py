from PIL import Image, ImageDraw
import numpy as np
import os

def fix_logo():
    input_path = r"c:\Users\el008\Desktop\2nd_project2\frontend\public\logo.png"
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    print(f"Processing {input_path}...")
    img = Image.open(input_path).convert("RGBA")
    
    # 1. Flood fill transparency from corners
    # (assumes corners are background)
    from PIL import Image, ImageChops

    def flood_fill_transparency(image, tolerance=50):
        # Create a seed image with same size
        width, height = image.size
        # Get background color from top-left pixel
        bg_color = image.getpixel((0, 0))
        
        # Calculate difference from background color
        diff = ImageChops.difference(image, Image.new("RGBA", image.size, bg_color))
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bbox = diff.getbbox()
        if bbox:
             return image.crop(bbox)
        return image

    # Using a more direct alpha replacement for white background
    data = np.array(img)
    r, g, b, a = data.T
    # White-ish pixels
    white_areas = (r > 230) & (g > 230) & (b > 230)
    data[..., 3][white_areas.T] = 0
    img_transparent = Image.fromarray(data)

    # Crop to content
    bbox = img_transparent.getbbox()
    if bbox:
        img_transparent = img_transparent.crop(bbox)
        print(f"Cropped to {bbox}")

    img_transparent.save(input_path)
    print("Logo refined successfully.")

if __name__ == "__main__":
    fix_logo()

import io
import logging

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    logger.warning("Pillow not installed. Image optimization disabled.")

def optimize_image_bytes(image_bytes: bytes, max_size: int = 2000, quality: int = 85) -> bytes:
    """
    Optimizes image for OCR:
    1. Resize to max dimension (default 2000px)
    2. Convert to Grayscale
    3. Compress as JPEG
    """
    if not HAS_PILLOW:
        return image_bytes
    
    try:
        # Check size if it's already small enough (e.g. < 500KB), maybe skip? 
        # But resizing helps OCR accuracy sometimes if too huge.
        
        # Open image
        img = Image.open(io.BytesIO(image_bytes))
        
        original_format = img.format
        w, h = img.size
        
        if max(w, h) <= max_size and img.mode == 'L' and len(image_bytes) < 1024 * 1024:
            # Already optimized enough?
            return image_bytes

        # Resize
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            # Use LANCZOS for best downsampling quality (text readability)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Convert to Grayscale (L) - Removes color noise, reduces size 3x
        if img.mode != 'L':
             img = img.convert('L')
             
        # Save to bytes
        output = io.BytesIO()
        # Force JPEG for maximum compression
        img.save(output, format='JPEG', quality=quality, optimize=True)
        optimized_bytes = output.getvalue()
        
        logger.info(f"Image Optimized: {len(image_bytes)/1024:.1f}KB -> {len(optimized_bytes)/1024:.1f}KB (Resized to {img.size})")
        return optimized_bytes
        
    except Exception as e:
        # If it's a PDF or non-image, Pillow will fail to identify. This is normal.
        if "cannot identify" in str(e) or "UnidentifiedImageError" in str(type(e)):
            logger.info("Skipping optimization for non-image file (likely PDF).")
        else:
            logger.warning(f"Image optimization failed: {e}")
        return image_bytes

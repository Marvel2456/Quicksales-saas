import os
import io
import uuid
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError


def optimize_image(image_file, max_dimension=1600, quality=82, prefix='img'):
    """
    Compresses and converts any uploaded image (products, avatars, logos, banners)
    to an optimized WebP image with automatic orientation correction and alpha support.
    """
    if not image_file:
        return None

    try:
        # Seek to beginning in case file pointer has moved
        if hasattr(image_file, 'seek'):
            image_file.seek(0)

        # Open image with Pillow
        img = Image.open(image_file)

        # 1. Correct EXIF orientation (e.g. mobile photos)
        img = ImageOps.exif_transpose(img) or img

        # 2. Handle transparency / color mode
        has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
        
        if has_alpha:
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

        # 3. Handle max dimensions
        if isinstance(max_dimension, (tuple, list)):
            max_w, max_h = max_dimension
        else:
            max_w = max_h = max_dimension

        width, height = img.size
        if width > max_w or height > max_h:
            ratio = min(max_w / width, max_h / height)
            new_width = max(1, int(width * ratio))
            new_height = max(1, int(height * ratio))
            
            # Use high-quality resampling filter
            resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
            img = img.resize((new_width, new_height), resample=resample_filter)

        # 4. Save to BytesIO buffer as WebP
        buffer = io.BytesIO()
        img.save(
            buffer,
            format='WEBP',
            quality=quality,
            method=6,
            lossless=False
        )
        buffer.seek(0)

        # 5. Generate clean .webp filename
        original_name = getattr(image_file, 'name', prefix)
        base_name, _ = os.path.splitext(os.path.basename(original_name))
        clean_base = "".join(c for c in base_name if c.isalnum() or c in ('-', '_')).rstrip() or prefix
        webp_filename = f"{clean_base}_{uuid.uuid4().hex[:8]}.webp"

        return ContentFile(buffer.getvalue(), name=webp_filename)

    except Exception as e:
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        raise ValidationError(f"Unable to process image: {str(e)}")


def optimize_product_image(image_file, max_dimension=1600, quality=82):
    """Product image optimization wrapper."""
    return optimize_image(image_file, max_dimension=max_dimension, quality=quality, prefix='product')


def compress_image_to_webp(image_file, max_size=None, max_dimension=1600, quality=82, prefix='img'):
    """Universal compression wrapper for logos, profiles, banners, etc."""
    dim = max_size if max_size is not None else max_dimension
    return optimize_image(image_file, max_dimension=dim, quality=quality, prefix=prefix)

import os
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

FOLDER = os.getenv('CLOUDINARY_FOLDER', 'proxy-commerce')

def ensure_images(row):
    """row[images]가 있으면 그대로, 없으면 MVP로 빈 목록.
    실제 운영은 정식 에셋 사용 권장.
    """
    imgs = (row.get('images') or '').strip()
    if imgs:
        return [u.strip() for u in imgs.split(',') if u.strip()]
    return []

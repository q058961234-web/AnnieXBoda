# plugins/ai/media_engine.py
# Authored By Certified Coders (c) 2026
# Enterprise Media Engine - H200 Optimized
# Integrates: OpenCV (Anime/4K), Rembg (AI Masking), MoviePy (Edit), FFmpeg (Render)

import os
import logging
import asyncio
import subprocess
import cv2
import numpy as np
from PIL import Image
from rembg import remove
from moviepy.editor import VideoFileClip, vfx

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_Media_Engine")
TEMP_DIR = "/dev/shm/AnnieDownloads"  # استخدام الرام ديسك للسرعة

# تأكد من وجود المجلد
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

# ------------------------------------------------------------------
# 1. IMAGE PROCESSORS (SYNC)
# ------------------------------------------------------------------

def _apply_anime_filter(file_path: str, output_path: str):
    """
    تحويل الصورة الى نمط كرتوني/انمي
    """
    img = cv2.imread(file_path)
    
    # تحسين الالوان وتنعيمها (Cartoon Effect)
    color = img
    for _ in range(2): # تقليل التكرار للسرعة
        color = cv2.bilateralFilter(color, d=9, sigmaColor=9, sigmaSpace=7)
    
    # تحديد الحواف (Edges)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 7)
    edges = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, blockSize=9, C=2
    )
    
    # دمج الالوان مع الحواف
    color = cv2.bitwise_and(color, color, mask=edges)
    
    # زيادة التشبع (Vibrance)
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = cv2.add(s, 40) # رفع التشبع
    v = cv2.add(v, 20) # رفع السطوع
    final_hsv = cv2.merge((h, s, v))
    final_img = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)
    
    cv2.imwrite(output_path, final_img)

def _remove_bg_image(file_path: str, output_path: str):
    """
    عزل الخلفية باستخدام AI (Rembg)
    """
    with open(file_path, "rb") as i:
        with open(output_path, "wb") as o:
            input_data = i.read()
            output_data = remove(input_data) # يعمل تلقائيا على GPU اذا توفر
            o.write(output_data)

def _upscale_image_4k(file_path: str, output_path: str):
    """
    رفع دقة الصورة
    """
    img = cv2.imread(file_path)
    # التكبير باستخدام Lanczos4 (الافضل للجودة)
    upscaled = cv2.resize(img, (3840, 2160), interpolation=cv2.INTER_LANCZOS4)
    # اضافة Sharpening خفيف بعد التكبير
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(upscaled, -1, kernel)
    cv2.imwrite(output_path, sharpened)

# ------------------------------------------------------------------
# 2. VIDEO PROCESSORS (SYNC)
# ------------------------------------------------------------------

def _upscale_video_ffmpeg(input_path: str, output_path: str):
    """
    رفع جودة الفيديو الى 4K باستخدام FFmpeg (Direct)
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "scale=3840:2160:flags=lanczos,unsharp=5:5:1.0:5:5:0.0",
        "-c:v", "libx264",
        "-preset", "fast",   # توازن بين السرعة والجودة
        "-crf", "20",
        "-c:a", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True)

def _edit_video_moviepy(input_path: str, output_path: str, instruction: str) -> str:
    """
    تعديلات الفيديو العامة (سرعة، عكس، صوت، الخ)
    """
    clip = VideoFileClip(input_path)
    final_output = output_path

    try:
        # استخراج الصوت
        if any(x in instruction for x in ["صوت", "اغنية", "mp3"]):
            final_output = input_path.rsplit(".", 1)[0] + ".mp3"
            clip.audio.write_audiofile(final_output)
            return final_output

        # تحويل لـ GIF
        if any(x in instruction for x in ["gif", "متحركة"]):
            final_output = input_path.rsplit(".", 1)[0] + ".gif"
            sub_clip = clip.subclip(0, min(7, clip.duration)) # 7 ثواني حد اقصى
            sub_clip.write_gif(final_output, fps=12)
            return final_output

        # فلاتر الفيديو
        if any(x in instruction for x in ["سريع", "تسريع"]):
            clip = clip.fx(vfx.speedx, 1.5)
        elif any(x in instruction for x in ["بطيء", "تبطيء"]):
            clip = clip.fx(vfx.speedx, 0.5)
        
        if any(x in instruction for x in ["عكس", "قلب"]):
            clip = clip.fx(vfx.time_mirror)
            
        if any(x in instruction for x in ["ابيض", "اسود"]):
            clip = clip.fx(vfx.blackwhite)

        # التصدير النهائي
        clip.write_videofile(
            final_output,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=4
        )
        return final_output

    finally:
        clip.close()

# ------------------------------------------------------------------
# MAIN ASYNC CONTROLLER
# ------------------------------------------------------------------

async def process_media(file_path: str, instruction: str) -> str:
    """
    واجهة التحكم الرئيسية التي تستدعيها Handlers
    """
    if not os.path.exists(file_path):
        return None

    instruction = instruction.lower().strip()
    loop = asyncio.get_running_loop()
    
    # تحديد المسار الناتج
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    ext = os.path.splitext(file_path)[1].lower()
    
    # تحديد النوع
    is_video = ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
    is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    
    output_path = f"{TEMP_DIR}/{base_name}_processed{ext}"
    if "عزل" in instruction and is_image:
        output_path = f"{TEMP_DIR}/{base_name}_no_bg.png"

    try:
        logger.info(f"Processing media: {instruction} on {file_path}")

        # --- معالجة الصور ---
        if is_image:
            if any(x in instruction for x in ["عزل", "خلفية", "png"]):
                await loop.run_in_executor(None, _remove_bg_image, file_path, output_path)
            
            elif any(x in instruction for x in ["انمي", "كرتون", "anime"]):
                await loop.run_in_executor(None, _apply_anime_filter, file_path, output_path)
            
            elif any(x in instruction for x in ["4k", "جودة", "hd"]):
                await loop.run_in_executor(None, _upscale_image_4k, file_path, output_path)
            
            else:
                # فلتر عام (افتراضي) لتحسين الصورة لو لم يحدد طلب
                # نستخدم نفس فلتر الانمي لكن بتأثير اخف او نعيد الصورة
                return file_path

        # --- معالجة الفيديو ---
        elif is_video:
            if any(x in instruction for x in ["4k", "جودة"]):
                await loop.run_in_executor(None, _upscale_video_ffmpeg, file_path, output_path)
            
            else:
                # استخدام MoviePy لباقي التعديلات (صوت، سرعة، الخ)
                result_path = await loop.run_in_executor(None, _edit_video_moviepy, file_path, output_path, instruction)
                return result_path

        return output_path

    except Exception as e:
        logger.error(f"Media Process Fatal Error: {e}")
        return None

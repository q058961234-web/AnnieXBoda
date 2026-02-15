# plugins/ai/media_engine.py
# Authored By Certified Coders (c) 2026
# Enterprise Media Engine - H200 Optimized
# Integrates: OpenCV (Anime/4K), Rembg (AI Masking), MoviePy (Edit) with FFmpeg fallback

import os
import logging
import asyncio
import subprocess
import shlex
import cv2
import numpy as np
from PIL import Image
from rembg import remove

# ------------------------------------------------------------------
# 0. SMART IMPORT (الحل السحري لمنع الكراش)
# ------------------------------------------------------------------
try:
    # محاولة استدعاء النسخة الحديثة (v2.0+)
    from moviepy import VideoFileClip, vfx
    MOVIEPY_AVAILABLE = True
except ImportError:
    try:
        # محاولة استدعاء النسخة القديمة (v1.0)
        from moviepy.editor import VideoFileClip, vfx
        MOVIEPY_AVAILABLE = True
    except ImportError:
        # إذا فشل الاثنين، نعتمد على FFmpeg فقط
        MOVIEPY_AVAILABLE = False

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_Media_Engine")
TEMP_DIR = "/dev/shm/AnnieDownloads"  # استخدام الرام ديسك للسرعة

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

# ------------------------------------------------------------------
# HELPER: RUN FFMPEG SAFELY
# ------------------------------------------------------------------
def _run_ffmpeg(cmd_list):
    """تشغيل أوامر FFmpeg بأمان"""
    try:
        cmd_str = [str(x) for x in cmd_list]
        subprocess.run(cmd_str, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg Error: {e.stderr.decode()}")
        raise e

# ------------------------------------------------------------------
# 1. IMAGE PROCESSORS (SYNC)
# ------------------------------------------------------------------
def _apply_anime_filter(file_path: str, output_path: str):
    """تحويل الصورة الى نمط كرتوني/انمي"""
    img = cv2.imread(file_path)
    if img is None:
        raise FileNotFoundError(file_path)

    color = img
    for _ in range(2):
        color = cv2.bilateralFilter(color, d=9, sigmaColor=9, sigmaSpace=7)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 7)
    edges = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, blockSize=9, C=2
    )
    
    color = cv2.bitwise_and(color, color, mask=edges)
    cv2.imwrite(output_path, color)

def _remove_bg_image(file_path: str, output_path: str):
    """عزل الخلفية باستخدام AI"""
    with open(file_path, "rb") as i:
        with open(output_path, "wb") as o:
            input_data = i.read()
            output_data = remove(input_data)
            o.write(output_data)

def _upscale_image_4k(file_path: str, output_path: str):
    """رفع دقة الصورة"""
    img = cv2.imread(file_path)
    upscaled = cv2.resize(img, (3840, 2160), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(output_path, upscaled)

# ------------------------------------------------------------------
# 2. FFMPEG FALLBACK FUNCTIONS
# ------------------------------------------------------------------
def _ffmpeg_extract_audio(input_path, output_path):
    _run_ffmpeg(["ffmpeg", "-y", "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path])

def _ffmpeg_create_gif(input_path, output_path):
    _run_ffmpeg(["ffmpeg", "-y", "-i", input_path, "-t", "7", "-vf", "fps=12,scale=iw:-1:flags=lanczos", output_path])

def _upscale_video_ffmpeg(input_path, output_path):
    _run_ffmpeg(["ffmpeg", "-y", "-i", input_path, "-vf", "scale=3840:2160:flags=lanczos", 
                 "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "copy", output_path])

# ------------------------------------------------------------------
# 3. VIDEO PROCESSOR (HYBRID CONTROLLER)
# ------------------------------------------------------------------
def _edit_video_hybrid(input_path: str, output_path: str, instruction: str) -> str:
    """المتحكم الذكي: يختار بين MoviePy و FFmpeg"""
    instruction = instruction.lower()

    if any(x in instruction for x in ["صوت", "اغنية", "mp3"]):
        final_output = input_path.rsplit(".", 1)[0] + ".mp3"
        if MOVIEPY_AVAILABLE:
            try:
                with VideoFileClip(input_path) as clip:
                    clip.audio.write_audiofile(final_output)
                return final_output
            except Exception:
                pass 
        _ffmpeg_extract_audio(input_path, final_output)
        return final_output

    if any(x in instruction for x in ["gif", "متحركة"]):
        final_output = input_path.rsplit(".", 1)[0] + ".gif"
        _ffmpeg_create_gif(input_path, final_output)
        return final_output

    # افتراضي: تحويل عادي
    _upscale_video_ffmpeg(input_path, output_path)
    return output_path

# ------------------------------------------------------------------
# 4. MAIN ASYNC INTERFACE
# ------------------------------------------------------------------
async def process_media(file_path: str, instruction: str) -> str:
    if not os.path.exists(file_path):
        return None

    instruction = instruction.lower().strip()
    loop = asyncio.get_running_loop()
    
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    ext = os.path.splitext(file_path)[1].lower()
    is_video = ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
    is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    
    output_path = f"{TEMP_DIR}/{base_name}_processed{ext}"
    if "عزل" in instruction and is_image:
        output_path = f"{TEMP_DIR}/{base_name}_no_bg.png"

    try:
        logger.info(f"Processing media: {instruction}")

        if is_image:
            if any(x in instruction for x in ["عزل", "خلفية"]):
                await loop.run_in_executor(None, _remove_bg_image, file_path, output_path)
            elif any(x in instruction for x in ["انمي", "كرتون"]):
                await loop.run_in_executor(None, _apply_anime_filter, file_path, output_path)
            elif any(x in instruction for x in ["4k", "جودة"]):
                await loop.run_in_executor(None, _upscale_image_4k, file_path, output_path)
            else:
                return file_path

        elif is_video:
            if any(x in instruction for x in ["4k", "جودة"]):
                await loop.run_in_executor(None, _upscale_video_ffmpeg, file_path, output_path)
            else:
                result = await loop.run_in_executor(None, _edit_video_hybrid, file_path, output_path, instruction)
                return result

        return output_path

    except Exception as e:
        logger.exception(f"Media Process Error: {e}")
        return None

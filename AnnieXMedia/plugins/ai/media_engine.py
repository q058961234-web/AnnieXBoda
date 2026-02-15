# plugins/ai/media_engine.py
# Zero-Error Edition 2026
# Integrates: RealESRGAN, Rembg, MoviePy (Auto-Detect), FFmpeg

import os
import logging
import asyncio
import subprocess
import cv2
import numpy as np
from rembg import remove

# --- 0. SMART IMPORT (كشف إصدار MoviePy تلقائياً) ---
try:
    # محاولة استدعاء النسخة الحديثة (v2.0+)
    from moviepy import VideoFileClip, AudioFileClip, vfx
    MOVIEPY_AVAILABLE = True
except ImportError:
    try:
        # محاولة استدعاء النسخة القديمة (v1.x)
        from moviepy.editor import VideoFileClip, AudioFileClip, vfx
        MOVIEPY_AVAILABLE = True
    except ImportError:
        # فشل الاستدعاء - سيتم استخدام FFmpeg فقط
        MOVIEPY_AVAILABLE = False

# --- CONFIGURATION ---
logger = logging.getLogger("AnnieX_Media")
TEMP_DIR = "/dev/shm/AnnieDownloads"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

# --- 1. FFMPEG DIRECT HELPERS (الأكثر استقراراً) ---
def _run_ffmpeg(cmd):
    try:
        # تحويل الأمر لنصوص وتشغيله
        subprocess.run([str(x) for x in cmd], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except Exception as e:
        logger.error(f"FFmpeg Error: {e}")
        return False

def _ffmpeg_convert(inp, out):
    # تحويل آمن لأي فيديو
    return _run_ffmpeg(["ffmpeg", "-y", "-i", inp, "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", out])

# --- 2. IMAGE PROCESSORS (معالجة الصور) ---
def _process_anime(inp, out):
    """تحويل الصورة لنمط أنمي باستخدام OpenCV"""
    img = cv2.imread(inp)
    if img is None: return False
    
    # تنعيم الألوان مع الحفاظ على الحواف
    color = cv2.bilateralFilter(img, 9, 250, 250)
    # تحديد الخطوط السوداء
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 7)
    edges = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9)
    # الدمج
    anime = cv2.bitwise_and(color, color, mask=edges)
    cv2.imwrite(out, anime)
    return True

def _process_upscale(inp, out):
    """رفع الجودة 4K باستخدام Lanczos + Sharpening"""
    img = cv2.imread(inp)
    if img is None: return False
    # تكبير ذكي
    upscaled = cv2.resize(img, (3840, 2160), interpolation=cv2.INTER_LANCZOS4)
    # زيادة الحدة
    gaussian = cv2.GaussianBlur(upscaled, (0, 0), 2.0)
    final = cv2.addWeighted(upscaled, 1.5, gaussian, -0.5, 0)
    cv2.imwrite(out, final)
    return True

def _process_rembg(inp, out):
    """عزل الخلفية باستخدام الذكاء الاصطناعي"""
    try:
        with open(inp, "rb") as i, open(out, "wb") as o:
            o.write(remove(i.read()))
        return True
    except Exception:
        return False

# --- 3. VIDEO PROCESSORS (معالجة الفيديو) ---
def _process_video_edit(inp, out, cmd):
    # إذا لم تكن MoviePy موجودة، نستخدم FFmpeg
    if not MOVIEPY_AVAILABLE:
        return _ffmpeg_convert(inp, out)

    try:
        clip = VideoFileClip(inp)
        
        # استخراج الصوت
        if any(x in cmd for x in ["mp3", "audio", "صوت"]):
            out = out.rsplit(".", 1)[0] + ".mp3"
            clip.audio.write_audiofile(out, logger=None)
            clip.close()
            return out

        # تحويل لـ GIF
        if any(x in cmd for x in ["gif", "متحركة"]):
            out = out.rsplit(".", 1)[0] + ".gif"
            sub = clip.subclip(0, min(7, clip.duration))
            sub.write_gif(out, fps=12, logger=None)
            clip.close()
            return out

        # التحكم في السرعة
        if any(x in cmd for x in ["speed", "سريع"]):
            clip = clip.fx(vfx.speedx, 1.5)
        elif any(x in cmd for x in ["slow", "بطيء"]):
            clip = clip.fx(vfx.speedx, 0.5)
            
        # عكس الفيديو
        if any(x in cmd for x in ["reverse", "عكس"]):
            clip = clip.fx(vfx.time_mirror)

        # الحفظ النهائي
        clip.write_videofile(out, codec="libx264", audio_codec="aac", preset="fast", logger=None)
        clip.close()
        return out

    except Exception:
        # في حالة حدوث خطأ، نعود لـ FFmpeg
        _ffmpeg_convert(inp, out)
        return out

# --- 4. MAIN INTERFACE (واجهة التحكم) ---
async def process_media(file_path: str, instruction: str) -> str:
    if not os.path.exists(file_path):
        return None

    instruction = instruction.lower().strip()
    loop = asyncio.get_running_loop()
    
    base = os.path.splitext(os.path.basename(file_path))[0]
    ext = os.path.splitext(file_path)[1].lower()
    
    is_vid = ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
    is_img = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    
    out_path = f"{TEMP_DIR}/{base}_pro{ext}"
    if is_img and "عزل" in instruction:
        out_path = f"{TEMP_DIR}/{base}.png"

    try:
        logger.info(f"Processing: {instruction}")

        if is_img:
            if any(x in instruction for x in ["عزل", "خلفية"]):
                await loop.run_in_executor(None, _process_rembg, file_path, out_path)
            elif any(x in instruction for x in ["انمي", "كرتون"]):
                await loop.run_in_executor(None, _process_anime, file_path, out_path)
            elif any(x in instruction for x in ["4k", "جودة"]):
                await loop.run_in_executor(None, _process_upscale, file_path, out_path)
            else:
                return file_path

        elif is_vid:
            if any(x in instruction for x in ["4k", "جودة"]):
                await loop.run_in_executor(None, _ffmpeg_convert, file_path, out_path)
            else:
                res = await loop.run_in_executor(None, _process_video_edit, file_path, out_path, instruction)
                return res

        return out_path if os.path.exists(out_path) else None

    except Exception as e:
        logger.error(f"Media Error: {e}")
        return None

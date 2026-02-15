# plugins/ai/media_engine.py
# Certified Studio Engine 2026 (H200 Optimized)
# Features: 8K Upscale, AI Background Swap (City/Black), Smart Compositing

import os
import logging
import asyncio
import subprocess
import cv2
import numpy as np
import requests
from rembg import remove
from PIL import Image
from io import BytesIO

# --- 0. SMART IMPORT LAYER ---
try:
    from moviepy import VideoFileClip, AudioFileClip, vfx
    import moviepy.video.fx.all as vfx_all
    MOVIEPY_AVAILABLE = True
except ImportError:
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, vfx
        import moviepy.video.fx.all as vfx_all
        MOVIEPY_AVAILABLE = True
    except ImportError:
        MOVIEPY_AVAILABLE = False

# --- CONFIGURATION ---
logger = logging.getLogger("AnnieX_Studio")
TEMP_DIR = "/dev/shm/AnnieDownloads"
CITY_BG_URL = "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?q=80&w=3840&auto=format&fit=crop"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

# --- 1. CORE PROCESSORS ---

def _download_asset(url):
    """تحميل أصول (خلفيات) في الرام مباشرة"""
    try:
        response = requests.get(url, timeout=10)
        img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except:
        return None

def _overlay_transparent(background, overlay, x, y):
    """دمج صورة معزولة على خلفية جديدة"""
    background_width = background.shape[1]
    background_height = background.shape[0]

    if x >= background_width or y >= background_height:
        return background

    h, w = overlay.shape[0], overlay.shape[1]

    if x + w > background_width:
        w = background_width - x
        overlay = overlay[:, :w]

    if y + h > background_height:
        h = background_height - y
        overlay = overlay[:h]

    if overlay.shape[2] < 4:
        overlay = np.concatenate(
            [
                overlay,
                np.ones((overlay.shape[0], overlay.shape[1], 1), dtype=overlay.dtype) * 255
            ],
            axis=2,
        )

    overlay_image = overlay[..., :3]
    mask = overlay[..., 3:] / 255.0

    background[y:y+h, x:x+w] = (1.0 - mask) * background[y:y+h, x:x+w] + mask * overlay_image

    return background

# --- 2. IMAGE EFFECTS ---

def _effect_city_bg(inp, out):
    """عزل الشخص ووضعه في مدينة"""
    # 1. قراءة الصورة وعزلها
    with open(inp, "rb") as i:
        input_data = i.read()
        subject_data = remove(input_data) # Returns PNG bytes
    
    # تحويل الـ Bytes لـ OpenCV Image
    subject_arr = np.asarray(bytearray(subject_data), dtype=np.uint8)
    subject = cv2.imdecode(subject_arr, cv2.IMREAD_UNCHANGED)
    
    # 2. تحميل خلفية المدينة
    city = _download_asset(CITY_BG_URL)
    if city is None: return False
    
    # 3. ضبط الأحجام (Fit Subject to City)
    h_bg, w_bg = city.shape[:2]
    h_fg, w_fg = subject.shape[:2]
    
    # تكبير/تصغير الشخص ليتناسب مع المدينة (مثلاً 80% من الارتفاع)
    scale = (h_bg * 0.85) / h_fg
    new_w = int(w_fg * scale)
    new_h = int(h_fg * scale)
    subject = cv2.resize(subject, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    # 4. التمركز
    x_offset = (w_bg - new_w) // 2
    y_offset = (h_bg - new_h) # الوقوف على الأرض
    
    final = _overlay_transparent(city, subject, x_offset, y_offset)
    cv2.imwrite(out, final)
    return True

def _effect_upscale(inp, out, quality="4k"):
    """رفع الجودة لـ 4K أو 8K"""
    img = cv2.imread(inp)
    if img is None: return False
    
    if "8k" in quality:
        target_res = (7680, 4320)
    else:
        target_res = (3840, 2160)
        
    # Lanczos Upscaling (الأفضل للدقة)
    upscaled = cv2.resize(img, target_res, interpolation=cv2.INTER_LANCZOS4)
    
    # Sharpening Filter (لإظهار التفاصيل بعد التكبير)
    gaussian = cv2.GaussianBlur(upscaled, (0, 0), 2.0)
    final = cv2.addWeighted(upscaled, 1.5, gaussian, -0.5, 0)
    
    cv2.imwrite(out, final)
    return True

# --- 3. VIDEO EFFECTS ---

def _video_black_bg(inp, out):
    """تحويل خلفية الفيديو للأسود (H200 Heavy Processing)"""
    if not MOVIEPY_AVAILABLE: return False
    
    try:
        clip = VideoFileClip(inp)
        
        # دالة لمعالجة كل فريم
        def process_frame(frame):
            # Frame يأتي كـ Numpy Array
            # نحوله لـ Bytes عشان Rembg
            is_success, buffer = cv2.imencode(".png", frame)
            if not is_success: return frame
            
            # العزل (هنا قوة H200 هتظهر)
            output_bytes = remove(buffer.tobytes())
            
            # تحويل الـ PNG الشفاف لـ خلفية سوداء
            img_rgba = cv2.imdecode(np.frombuffer(output_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            
            # إنشاء خلفية سوداء
            h, w = img_rgba.shape[:2]
            black_bg = np.zeros((h, w, 3), dtype=np.uint8)
            
            # الدمج
            return _overlay_transparent(black_bg, img_rgba, 0, 0)

        # تطبيق الفلتر
        new_clip = clip.fl_image(process_frame)
        new_clip.write_videofile(out, codec="libx264", audio_codec="aac", preset="fast", logger=None)
        return True
    except Exception as e:
        logger.error(f"Video BG Error: {e}")
        return False

def _video_upscale_ffmpeg(inp, out, quality="4k"):
    """رفع جودة الفيديو باستخدام FFmpeg Lanczos"""
    scale = "scale=7680:4320" if "8k" in quality else "scale=3840:2160"
    cmd = [
        "ffmpeg", "-y", "-i", inp,
        "-vf", f"{scale}:flags=lanczos,unsharp=5:5:1.0:5:5:0.0", # رفع الجودة + زيادة الحدة
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", # جودة عالية
        "-c:a", "copy",
        out
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except: return False

# --- 4. MAIN INTERFACE ---

async def process_media(file_path: str, instruction: str) -> str:
    if not os.path.exists(file_path): return None
    
    instruction = instruction.lower().strip()
    loop = asyncio.get_running_loop()
    
    base = os.path.splitext(os.path.basename(file_path))[0]
    ext = os.path.splitext(file_path)[1].lower()
    
    is_vid = ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
    is_img = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    
    out_path = f"{TEMP_DIR}/{base}_pro{ext}"
    
    try:
        logger.info(f"🎨 Studio Job: {instruction} | Type: {'Video' if is_vid else 'Image'}")

        if is_img:
            if "مدينة" in instruction or "city" in instruction:
                await loop.run_in_executor(None, _effect_city_bg, file_path, out_path)
            elif "8k" in instruction:
                await loop.run_in_executor(None, _effect_upscale, file_path, out_path, "8k")
            elif "4k" in instruction:
                await loop.run_in_executor(None, _effect_upscale, file_path, out_path, "4k")
            elif "عزل" in instruction or "bg" in instruction:
                # العزل العادي (PNG شفاف)
                out_path = f"{TEMP_DIR}/{base}.png"
                with open(file_path, "rb") as i, open(out_path, "wb") as o:
                    o.write(remove(i.read()))
            elif "انمي" in instruction:
                # فلتر الأنمي القديم
                pass # (ممكن تضيف كود الانمي هنا لو حابب)
            else:
                return file_path

        elif is_vid:
            if "سوداء" in instruction or "black" in instruction:
                await loop.run_in_executor(None, _video_black_bg, file_path, out_path)
            elif "8k" in instruction:
                await loop.run_in_executor(None, _video_upscale_ffmpeg, file_path, out_path, "8k")
            elif "4k" in instruction:
                await loop.run_in_executor(None, _video_upscale_ffmpeg, file_path, out_path, "4k")
            else:
                return file_path

        return out_path if os.path.exists(out_path) else None

    except Exception as e:
        logger.error(f"Studio Error: {e}")
        return None

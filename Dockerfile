# ==================================================
# 🏗️ المرحلة 1: الأساس (NVIDIA CUDA 12.6 - Ubuntu 24.04)
# ==================================================
FROM nvidia/cuda:12.6.0-runtime-ubuntu24.04

# ==================================================
# ⚡ إعدادات البيئة (بدون تدخل منك)
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # تفعيل الكارت غصب عن النظام
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    # مسارات الذكاء الاصطناعي
    OLLAMA_MODELS="/app/ollama_models" \
    OLLAMA_HOST="0.0.0.0" \
    # تحسينات بايثون 3.13
    PYTHON_GIL=0

WORKDIR /app

# ==================================================
# 🛠️ تسطيب الأدوات وتجهيز Python 3.13
# ==================================================
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    software-properties-common wget curl git \
    aria2 zstd xz-utils unzip zip \
    libgl1 libglib2.0-0 libsm6 libxext6 \
    imagemagick ghostscript libsndfile1 fontconfig \
    build-essential libffi-dev cmake && \
    # إضافة بايثون 3.13
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.13 python3.13-dev python3.13-venv python3-pip && \
    # تعيين بايثون 3.13 كافتراضي
    ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python && \
    # إصلاح مشاكل ImageMagick
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml || true && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🎥 تنزيل FFmpeg (نسخة H200 NVENC)
# ==================================================
RUN wget -q https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz && \
    tar -xf ffmpeg-master-latest-linux64-gpl.tar.xz && \
    cp ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /usr/bin/ffmpeg && \
    cp ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/bin/ffprobe && \
    chmod +x /usr/bin/ffmpeg /usr/bin/ffprobe && \
    rm -rf ffmpeg-master-latest-linux64-gpl*

# ==================================================
# 🧠 تجهيز Ollama (أوتوماتيك)
# ==================================================
RUN curl -fsSL https://ollama.com/install.sh | sh

# ==================================================
# 🐍 تسطيب المكتبات
# ==================================================
RUN python3 -m pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# تنظيف المتطلبات وتسطيبها
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تسطيب المكتبات الثقيلة يدوياً لضمان التوافق
RUN pip install --no-cache-dir \
    "numpy>=2.0.0" opencv-python-headless rembg[gpu] uvloop g4f curl_cffi ollama moviepy \
    https://github.com/yt-dlp/yt-dlp/archive/master.zip

# ==================================================
# 📂 نقل الملفات وتجهيز المجلدات
# ==================================================
COPY . .

# إنشاء مجلدات العمل وإعطاء صلاحيات كاملة (عشان لو مفيش رووت)
RUN mkdir -p /app/downloads /app/cache /app/ollama_models && \
    chmod -R 777 /app

# ==================================================
# 🚀 سكريبت التشغيل الذكي (هو ده اللي بيحل مشكلة عدم وجود تيرمنال)
# ==================================================
# السكريبت ده هيشتغل أول ما البوت يترفع، وهيعمل كل حاجة بالنيابة عنك
RUN echo '#!/bin/bash\n\
\n\
echo "🟢 [Auto-Pilot] Starting System..."\n\
\n\
# 1. تشغيل Ollama في الخلفية\n\
ollama serve > /app/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
# 2. تشغيل البوت فوراً (عشان المنصة تفتكره شغال ومتقفلوش)\n\
# بنستخدم Free-Threading لو متاح لسرعة خرافية\n\
export PYTHON_GIL=0\n\
python3 run.py &\n\
BOT_PID=$!\n\
\n\
echo "✅ [Bot] Started with PID $BOT_PID"\n\
\n\
# 3. تحميل موديل الذكاء الاصطناعي في الخلفية (مش هيعطل البوت)\n\
echo "🧠 [AI] Downloading DeepSeek Model in background..."\n\
(sleep 10 && ollama pull deepseek-r1:70b > /dev/null 2>&1) &\n\
\n\
# 4. مراقبة البوت (لو وقع السكريبت يقفل والمنصة تعمل ريستارت)\n\
wait $BOT_PID\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

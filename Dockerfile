# ==================================================
# 🏗️ المرحلة 1: NVIDIA CUDA 12.6 - Ubuntu 24.04
# ==================================================
FROM nvidia/cuda:12.6.0-runtime-ubuntu24.04

# ==================================================
# ⚡ إعدادات البيئة
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # تفعيل الكارت
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    # مسارات الذكاء الاصطناعي
    OLLAMA_MODELS="/app/ollama_models" \
    OLLAMA_HOST="0.0.0.0"

WORKDIR /app

# ==================================================
# 🛠️ تسطيب الأدوات + Node.js + pciutils
# ==================================================
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    software-properties-common wget curl git \
    aria2 zstd xz-utils unzip zip \
    libgl1 libglib2.0-0 libsm6 libxext6 \
    imagemagick ghostscript libsndfile1 fontconfig \
    build-essential libffi-dev cmake \
    # أدوات الهاردوير عشان Ollama يشوف الـ GPU
    pciutils lshw \
    # Node.js عشان اليوتيوب
    nodejs npm && \
    # إضافة بايثون 3.13
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.13 python3.13-dev python3.13-venv \
    # ❌ شيلنا python3-pip عشان هنسطبه يدوياً ونحل المشكلة
    && \
    # ربط الروابط الرمزية
    ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python && \
    # إصلاح ImageMagick
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml || true && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🔧 إصلاح PIP (الحل الجذري لمشكلة RECORD file)
# ==================================================
# بننزل سكربت التسطيب الرسمي ونشغله بذكاء
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.13 --break-system-packages

# ==================================================
# 🎥 تنزيل FFmpeg (H200 NVENC)
# ==================================================
RUN wget -q https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz && \
    tar -xf ffmpeg-master-latest-linux64-gpl.tar.xz && \
    cp ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /usr/bin/ffmpeg && \
    cp ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/bin/ffprobe && \
    chmod +x /usr/bin/ffmpeg /usr/bin/ffprobe && \
    rm -rf ffmpeg-master-latest-linux64-gpl*

# ==================================================
# 🧠 تجهيز Ollama
# ==================================================
RUN curl -fsSL https://ollama.com/install.sh | sh

# ==================================================
# 🐍 تسطيب المكتبات
# ==================================================
COPY requirements.txt .

# تنظيف المتطلبات وتسطيبها (مع استخدام --break-system-packages عشان Ubuntu 24.04)
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir --break-system-packages -r filtered.txt

# تسطيب المكتبات الثقيلة + تحديث yt-dlp
RUN pip install --no-cache-dir --break-system-packages \
    "numpy>=2.0.0" opencv-python-headless rembg[gpu] uvloop g4f curl_cffi ollama moviepy \
    https://github.com/yt-dlp/yt-dlp/archive/master.zip

# ==================================================
# 📂 نقل الملفات وتجهيز المجلدات
# ==================================================
COPY . .

RUN mkdir -p /app/downloads /app/cache /app/ollama_models && \
    chmod -R 777 /app

# ==================================================
# 🚀 سكريبت التشغيل (Auto-Pilot)
# ==================================================
RUN echo '#!/bin/bash\n\
\n\
echo "🟢 [Auto-Pilot] Starting System..."\n\
\n\
# 1. تشغيل Ollama\n\
ollama serve > /app/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
# 2. تشغيل البوت\n\
python3 run.py &\n\
BOT_PID=$!\n\
\n\
echo "✅ [Bot] Started with PID $BOT_PID"\n\
\n\
# 3. تحميل موديل الذكاء الاصطناعي\n\
echo "🧠 [AI] Downloading DeepSeek Model in background..."\n\
(sleep 15 && ollama pull deepseek-r1:70b > /dev/null 2>&1) &\n\
\n\
wait $BOT_PID\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

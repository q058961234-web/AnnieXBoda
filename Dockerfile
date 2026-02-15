FROM python:3.13-slim

# ==================================================
# ⚡ إعدادات البيئة وحفظ الموديلات
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    OLLAMA_MODELS="/data/ollama" \
    OLLAMA_HOST="0.0.0.0" \
    IMAGEMAGICK_BINARY="/usr/bin/convert"

WORKDIR /app

# ==================================================
# 🛠️ تثبيت أدوات النظام (تم إصلاح الخطأ هنا)
# ==================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # أدوات أساسية (Git و Curl ضروريين جداً)
    curl git wget gnupg2 unzip zip procps \
    # أدوات البناء
    build-essential libffi-dev zlib1g-dev \
    # مكتبات الميديا (تم حذف libgl1-mesa-glx المعطوبة)
    ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 \
    imagemagick ghostscript \
    libsndfile1 fontconfig && \
    # إصلاح ImageMagick
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml || true && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🧠 تثبيت Ollama
# ==================================================
RUN curl -fsSL https://ollama.com/install.sh | sh

# ==================================================
# 🐍 تثبيت المكتبات
# ==================================================
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# فلتر لتجنب تضارب التسميات
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تثبيت يدوي للمكتبات الحرجة
RUN pip install --no-cache-dir \
    opencv-python-headless rembg[gpu] \
    numpy pillow uvloop g4f curl_cffi ollama moviepy

# ==================================================
# 📂 نسخ الملفات والتشغيل
# ==================================================
COPY . .

RUN mkdir -p /dev/shm/AnnieDownloads && chmod 777 /dev/shm/AnnieDownloads
RUN mkdir -p /data/ollama && chmod 777 /data/ollama

# سكريبت التشغيل الذكي
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [System] Starting Ollama Service..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
\n\
echo "⏳ [System] Waiting for AI Engine..."\n\
sleep 5\n\
\n\
if ollama list | grep -q "deepseek-r1:70b"; then\n\
    echo "✅ [AI] Model found in storage! Skipping download."\n\
else\n\
    echo "⚠️ [AI] Model not found. Pulling DeepSeek-R1 70B..."\n\
    ollama pull deepseek-r1:70b\n\
fi\n\
\n\
echo "🟢 [Bot] Launching AnnieXBoda Core..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

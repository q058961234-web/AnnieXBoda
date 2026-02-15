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
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    OLLAMA_MODELS="/app/ollama_models" \
    OLLAMA_HOST="0.0.0.0"

WORKDIR /app

# ==================================================
# 🛠️ تسطيب الأدوات (Node.js + Python 3.13)
# ==================================================
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    software-properties-common wget curl git \
    aria2 zstd xz-utils unzip zip \
    libgl1 libglib2.0-0 libsm6 libxext6 \
    imagemagick ghostscript libsndfile1 fontconfig \
    build-essential libffi-dev cmake \
    pciutils lshw nodejs npm && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.13 python3.13-dev python3.13-venv \
    && \
    ln -sf /usr/bin/python3.13 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.13 /usr/bin/python && \
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml || true && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🔧 إصلاح PIP
# ==================================================
RUN curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python3.13 get-pip.py --break-system-packages && \
    rm get-pip.py

# ==================================================
# 🎥 تنزيل FFmpeg
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

# 1. تنظيف وتسطيب المتطلبات
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir --break-system-packages --ignore-installed -r filtered.txt

# 2. تسطيب المكتبات الثقيلة + py-yt-search (المكتبة الجديدة)
RUN pip install --no-cache-dir --break-system-packages --ignore-installed \
    "numpy>=2.0.0" opencv-python-headless rembg[gpu] uvloop g4f curl_cffi ollama moviepy \
    py-yt-search \
    https://github.com/yt-dlp/yt-dlp/archive/master.zip

# ==================================================
# 📂 التجهيز النهائي
# ==================================================
COPY . .

RUN mkdir -p /app/downloads /app/cache /app/ollama_models && \
    chmod -R 777 /app

# ==================================================
# 🚀 التشغيل
# ==================================================
RUN echo '#!/bin/bash\n\
\n\
echo "🟢 [System] Starting..."\n\
ollama serve > /app/ollama.log 2>&1 &\n\
sleep 5\n\
python3 run.py &\n\
BOT_PID=$!\n\
echo "✅ [Bot] Started (PID: $BOT_PID)"\n\
(sleep 15 && ollama pull deepseek-r1:70b > /dev/null 2>&1) &\n\
wait $BOT_PID\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

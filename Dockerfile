FROM python:3.13-slim

# ==================================================
# ⚡ إعدادات البيئة (الأداء الأقصى)
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # توجيه الموديلات للهارد الدائم
    OLLAMA_MODELS="/data/ollama" \
    OLLAMA_HOST="0.0.0.0" \
    IMAGEMAGICK_BINARY="/usr/bin/convert"

WORKDIR /app

# ==================================================
# 🛠️ تثبيت أدوات النظام (شامل aria2 و zstd)
# ==================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # أدوات الشبكة والتحميل السريع
    curl git wget aria2 gnupg2 unzip zip procps zstd \
    # أدوات البناء الضرورية (عشان ntgcalls تتسطب صح)
    build-essential libffi-dev zlib1g-dev cmake \
    # مكتبات الميديا والجرافيك (بدون كراش)
    ffmpeg libsm6 libxext6 libgl1 libglib2.0-0 \
    imagemagick ghostscript \
    # مكتبات الصوت والخطوط
    libsndfile1 fontconfig && \
    # ✅ إصلاح سياسة ImageMagick (الجوكر *)
    sed -i 's/none/read,write/g' /etc/ImageMagick-*/policy.xml || true && \
    # تنظيف لتقليل الحجم
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🧠 تثبيت محرك الذكاء الاصطناعي (Ollama)
# ==================================================
RUN curl -fsSL https://ollama.com/install.sh | sh

# ==================================================
# 🐍 تثبيت مكتبات البايثون
# ==================================================
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# فلتر لمنع تضارب المكتبات القديمة
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تثبيت يدوي للمكتبات الحرجة لضمان وجودها
RUN pip install --no-cache-dir \
    opencv-python-headless rembg[gpu] \
    numpy pillow uvloop g4f curl_cffi ollama moviepy

# ==================================================
# 📂 نسخ ملفات البوت وتجهيز المجلدات
# ==================================================
COPY . .

# إنشاء مجلدات الرام (للسرعة) والهارد (للحفظ)
RUN mkdir -p /dev/shm/AnnieDownloads && chmod 777 /dev/shm/AnnieDownloads
RUN mkdir -p /data/ollama && chmod 777 /data/ollama

# ==================================================
# 🚀 سكريبت الإقلاع المتوازي (Parallel Boot)
# ==================================================
# هذا السكريبت يمنع كويب من قتل البوت أثناء التحميل
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [TitanOS] Starting Ollama Service..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
\n\
echo "🟢 [TitanOS] Starting Bot Interface (Opening Port 8000)..."\n\
# نشغل البوت في الخلفية فوراً عشان الـ Health Check ينجح\n\
python3 run.py &\n\
PID=$!\n\
\n\
sleep 10\n\
\n\
echo "🔵 [TitanOS] Checking AI Models..."\n\
if ollama list | grep -q "deepseek-r1:70b"; then\n\
    echo "✅ [AI] Model found in persistent storage! Ready to rock."\n\
else\n\
    echo "⚠️ [AI] Model not found. Downloading DeepSeek-R1 70B (Background)..."\n\
    # التحميل هيتم والبوت شغال، عشان السيرفر ميفصلش\n\
    ollama pull deepseek-r1:70b\n\
fi\n\
\n\
# مراقبة البوت لضمان استمرار عمل الحاوية\n\
wait $PID\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

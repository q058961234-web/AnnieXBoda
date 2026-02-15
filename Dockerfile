FROM python:3.13-slim

# ==================================================
# ⚡ إعدادات البيئة وحفظ الموديلات
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # ✅ هنا السر: توجيه أولاما لحفظ الموديلات في مجلد دائم لعدم فقدان الـ 42 جيجا
    OLLAMA_MODELS="/data/ollama" \
    OLLAMA_HOST="0.0.0.0" \
    IMAGEMAGICK_BINARY="/usr/bin/convert"

WORKDIR /app

# ==================================================
# 🛠️ تثبيت أدوات النظام (لمنع الكراش والريستارت)
# ==================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # أدوات التحميل والشبكة
    curl git wget gnupg2 unzip zip procps \
    # أدوات البناء الضرورية للبايثون
    build-essential libffi-dev zlib1g-dev \
    # مكتبات الميديا والجرافيك (لحل مشاكل OpenCV و MoviePy)
    ffmpeg libsm6 libxext6 libgl1-mesa-glx libglib2.0-0 \
    imagemagick ghostscript \
    # مكتبات الصوت والخطوط
    libsndfile1 fontconfig && \
    # ✅ إصلاح سياسة ImageMagick للسماح بالكتابة على الفيديو
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml || true && \
    # تنظيف الكاش لتقليل حجم الصورة
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

# خطوة ذكية: فلترة المكتبات المتضاربة قبل التثبيت (مثل py-tgcalls القديمة)
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

# إنشاء مجلد التخزين المؤقت في الرام (للسرعة القصوى في المعالجة)
RUN mkdir -p /dev/shm/AnnieDownloads && chmod 777 /dev/shm/AnnieDownloads

# إنشاء مجلد التخزين الدائم للذكاء الاصطناعي (عشان الموديل ما يتمسحش)
RUN mkdir -p /data/ollama && chmod 777 /data/ollama

# ==================================================
# 🚀 سكريبت التشغيل الذكي (Smart Start Script)
# ==================================================
# هذا السكريبت يفحص: هل الموديل موجود في الهارد؟ 
# - لو موجود: يشغل البوت علطول (توفير وقت ورصيد).
# - لو مش موجود: يحمله لأول مرة فقط.
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [System] Starting Ollama Service..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
\n\
echo "⏳ [System] Waiting for AI Engine to wake up..."\n\
sleep 5\n\
\n\
# ✅ التحقق الذكي: هل الموديل موجود؟\n\
if ollama list | grep -q "deepseek-r1:70b"; then\n\
    echo "✅ [AI] Model found in persistent storage! Skipping download. 🚀"\n\
else\n\
    echo "⚠️ [AI] Model not found. Pulling DeepSeek-R1 70B (This happens ONLY once)..."\n\
    echo "☕ This might take 5-10 minutes depending on speed..."\n\
    ollama pull deepseek-r1:70b\n\
fi\n\
\n\
echo "🟢 [Bot] Launching AnnieXBoda Core..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

# نقطة الانطلاق
CMD ["./start.sh"]

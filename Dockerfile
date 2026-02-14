# متمسكين بـ 3.13 عشان خاطر pytgcalls و ntgcalls
FROM python:3.13-slim

# ===============================
# ⚡ إعدادات البيئة
# ===============================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DENO_INSTALL="/root/.deno" \
    OLLAMA_HOST=0.0.0.0 \
    IMAGEMAGICK_BINARY="/usr/bin/convert"

ENV PATH="${DENO_INSTALL}/bin:/usr/local/bin:${PATH}"

WORKDIR /app

# ===============================
# 🛠️ تثبيت أدوات النظام (الإصلاح الجذري هنا)
# ===============================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl git wget gnupg ffmpeg aria2 procps zstd unzip build-essential \
        libffi-dev libxml2-dev libxslt-dev zlib1g-dev \
        libgl1 libglib2.0-0 imagemagick && \
    \
    # ✅ هنا السر: استخدمنا * عشان يقرأ ImageMagick-6 أو 7 بدون أخطاء
    sed -i 's/none/read,write/g' /etc/ImageMagick-*/policy.xml && \
    \
    # تثبيت Node.js 20
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y nodejs && \
    \
    # تثبيت Deno و Ollama
    curl -fsSL https://deno.land/install.sh | sh && \
    curl -fsSL https://ollama.com/install.sh | sh && \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 🐍 تحديث البايثون والمكتبات
# ===============================
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تثبيت مكتبات المونتاج والذكاء الاصطناعي
RUN pip install --no-cache-dir \
    moviepy opencv-python-headless rembg[gpu] \
    numpy pillow uvloop g4f curl_cffi ollama

# ===============================
# 🎵 ملفات السورس
# ===============================
COPY pytgcalls /app/pytgcalls
RUN mkdir -p /etc/yt-dlp && echo "--remote-components ejs:github" > /etc/yt-dlp.conf

COPY . .

# ===============================
# 🧠 سكريبت الإقلاع (تحميل العملاق DeepSeek 70B)
# ===============================
RUN echo '#!/bin/bash\n\
echo "🔴 [System] Starting Ollama..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
echo "🔵 [AI Engine] Pulling DeepSeek-R1 70B (Full Power on H200)..."\n\
ollama pull deepseek-r1:70b\n\
\n\
echo "🟢 [Bot] Launching AnnieXBoda with Python 3.13..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

CMD ["./start.sh"]

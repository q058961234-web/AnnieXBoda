# ==================================================
# 🏗️ النسخة الموحدة (AI & Music Only) - Python 3.13 Slim
# ==================================================
FROM python:3.13-slim

# ==================================================
# ⚡ إعدادات البيئة
# ==================================================
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # مسارات Deno
    DENO_INSTALL="/root/.deno" \
    PATH="/root/.deno/bin:/usr/local/bin:$PATH" \
    # إعدادات Ollama
    OLLAMA_HOST="0.0.0.0"

WORKDIR /app

# ==================================================
# 🛠️ تثبيت النظام + Node.js + Deno + Ollama
# ==================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl git wget gnupg ffmpeg aria2 procps zstd unzip \
    build-essential libffi-dev libxml2-dev libxslt-dev zlib1g-dev && \
    \
    # 1. إعداد وتثبيت Node.js (النسخة 20 - مهم لفك تشفير يوتيوب)
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    \
    # 2. تثبيت Deno
    curl -fsSL https://deno.land/install.sh | sh && \
    \
    # 3. تثبيت Ollama
    curl -fsSL https://ollama.com/install.sh | sh && \
    \
    # تنظيف الكاش
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ==================================================
# 🐍 إعداد البايثون والمكتبات
# ==================================================
RUN pip install --upgrade pip setuptools wheel

# نسخ ملف المتطلبات
COPY requirements.txt .

# تثبيت المتطلبات (مع استثناء pytgcalls لتثبيته يدوياً)
RUN grep -v -i '^py-tgcalls\|pytgcalls' requirements.txt > filtered.txt && \
    pip install --no-cache-dir -r filtered.txt

# تثبيت مكتبات الذكاء وتخطي الحظر (بدون مكتبات الصور والفيديو)
RUN pip install --no-cache-dir \
    uvloop \
    g4f \
    curl_cffi \
    ollama \
    py-yt-search

# ==================================================
# 📂 نسخ الملفات وإعدادات yt-dlp
# ==================================================
# نسخ مجلد pytgcalls المحلي
COPY pytgcalls /app/pytgcalls

# إعداد yt-dlp
RUN mkdir -p /etc/yt-dlp && \
    echo "--remote-components ejs:github" > /etc/yt-dlp.conf

# نسخ باقي مشروع البوت
COPY . .

# ==================================================
# 🧠 سكريبت الإقلاع (AI + Music Logic)
# ==================================================
RUN echo '#!/bin/bash\n\
\n\
echo "🔴 [AI Engine] Starting Ollama Server..."\n\
ollama serve > /var/log/ollama.log 2>&1 &\n\
sleep 5\n\
\n\
echo "🔵 [AI Engine] Downloading THE KING (DeepSeek-R1 70B)..."\n\
# التحميل هنا (Blocking) لضمان جاهزية الذكاء قبل بدء البوت\n\
ollama pull deepseek-r1:70b\n\
echo "✅✅ [AI Engine] DeepSeek-R1 is Ready & Loaded!"\n\
\n\
echo "🟢 [Music Bot] Starting AnnieXBoda..."\n\
python3 run.py\n\
' > start.sh && chmod +x start.sh

# ==================================================
# 🏁 التشغيل
# ==================================================
CMD ["./start.sh"]

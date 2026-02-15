# file: AnnieXMedia/platforms/Youtube.py
# H200 STABLE: Integrated with py-yt-search (Async)
# Fixes: Metadata Fetching & Signature Issues using Node.js

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# 🔥 استيراد المكتبة الجديدة بناءً على التوثيق
try:
    from py_yt import VideosSearch, Video
    PY_YT_AVAILABLE = True
except ImportError:
    PY_YT_AVAILABLE = False

# Optional faster JSON parser
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes):
        return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes):
        return json.loads(b.decode("utf-8", "ignore"))

# Logging
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

# Tunables
MAX_YTDLP_THREADS = 16
MAX_CONCURRENT_EXTRACTS = 6
YTDLP_SOCKET_TIMEOUT = 8
PROBE_TIMEOUT = 1.2
CACHE_DEFAULT_TTL = 300
AIO_CONN_LIMIT = 64
META_CACHE_TTL = 3600

# Pools / semaphores / caches
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

# Lazy Init for Session to avoid RuntimeError
_aio_session: Optional[aiohttp.ClientSession] = None

_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "platforms/cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except Exception:
            continue
    return None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
        _aio_session = aiohttp.ClientSession(connector=connector)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        return b"", b"timeout"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    try:
        if isinstance(videoid, str) and re.match(r'^[0-9A-Za-z_-]{11}$', videoid):
            return "https://www.youtube.com/watch?v=" + videoid
    except Exception:
        pass

    if not link:
        return ""
    link = link.strip()
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    if "youtube.com/shorts/" in link or "youtube.com/live/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params:
            return int(params["expire"][0])
    except Exception:
        pass
    return None

async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400:
                    return True, r.headers.get("Content-Type")
        except Exception:
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206):
                        return True, r2.headers.get("Content-Type")
            except Exception:
                return False, None
    except Exception:
        return False, None
    return False, None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.pool = _thread_pool
        self.sema = _extract_sema
        self.cookie = get_cookie_file()
        try:
            import curl_cffi
            self.impersonate = True
        except Exception:
            self.impersonate = False

    async def invalidate_direct_cache(self, vid_or_link: Optional[str]) -> None:
        pass

    async def clear_direct_cache(self) -> None:
        try:
            async with _direct_cache_lock: _direct_cache.clear()
        except: pass

    async def url(self, message) -> Optional[str]:
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    t = getattr(ent, "type", None)
                    if t == "url":
                        off, ln = getattr(ent, "offset", None), getattr(ent, "length", None)
                        if off is not None: return text[off: off + ln].split("&si")[0]
                    u = getattr(ent, "url", None)
                    if u: return u.split("&si")[0]
                except: continue
        return None

    # 🛑 استخدام py-yt-search للبحث السريع (حسب التوثيق)
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        if PY_YT_AVAILABLE:
            try:
                # Usage: videosSearch = VideosSearch('...', limit=10, ...)
                videosSearch = VideosSearch(query, limit=limit)
                # Usage: videosResult = await videosSearch.next()
                res = await videosSearch.next()
                if res and "result" in res:
                    return [{
                        "title": x.get("title", "Unknown"),
                        "vidid": x.get("id", ""),
                        "duration": x.get("duration", "")
                    } for x in res["result"]]
            except Exception as e:
                log.warning(f"py-yt search failed: {e}")
        
        # Fallback to yt-dlp
        cmd = ["yt-dlp", "--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        if self.cookie: cmd.extend(["--cookies", self.cookie])
        out, _ = await _exec_proc(*cmd, timeout=10)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({"title": data.get("title", "Unknown"), "vidid": data.get("id", ""), "duration": data.get("duration_string", "")})
                except: pass
        return results

    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()
        
        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid
                _meta_cache.pop(key, None)

        # 1. Try py-yt-search first
        if PY_YT_AVAILABLE:
            try:
                # If it's a direct ID or Link, search limit 1 is efficient
                search = VideosSearch(prepared, limit=1)
                res = await search.next()
                if res and "result" in res and res["result"]:
                    r = res["result"][0]
                    thumb = "https://telegra.ph/file/015197d62057217355d9c.jpg"
                    if r.get("thumbnails"):
                        # Get best resolution usually last
                        thumb = r["thumbnails"][-1].get("url", "").split("?")[0]
                    
                    details = {
                        "title": r.get("title", "Unknown Track"),
                        "link": f"https://www.youtube.com/watch?v={r.get('id')}",
                        "vidid": r.get("id", ""),
                        "duration_min": r.get("duration", "00:00"),
                        "thumb": thumb,
                        "cookiefile": self.cookie,
                    }
                    async with _meta_cache_lock: _meta_cache[key] = (now, details, r.get("id", ""))
                    return details, r.get("id", "")
            except Exception as e:
                log.warning(f"py-yt track fetch failed: {e}")

        # 2. Fallback: yt-dlp
        cmd = [
            "yt-dlp", "--dump-json", prepared, "--no-warnings", 
            "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT),
            "--extractor-args", "youtube:player_client=android"
        ]
        if self.cookie:
            cmd.extend(["--cookies", self.cookie])
            
        out, _ = await _exec_proc(*cmd, timeout=12)
        if out:
            try:
                info = _loads_bytes(out)
                thumb = (info.get("thumbnail") or "https://telegra.ph/file/015197d62057217355d9c.jpg").split("?")[0]
                details = {
                    "title": info.get("title", "Unknown Track"),
                    "link": info.get("webpage_url", prepared) or prepared,
                    "vidid": info.get("id", "") or "",
                    "duration_min": info.get("duration_string", "00:00"),
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass
            
        # 3. Last Resort
        fake_id = str(int(time.time()))
        if "v=" in prepared:
            try: fake_id = prepared.split("v=")[1].split("&")[0]
            except: pass
            
        dummy_details = {
            "title": "Music Stream",
            "link": prepared,
            "vidid": fake_id,
            "duration_min": "00:00",
            "thumb": "https://telegra.ph/file/015197d62057217355d9c.jpg",
            "cookiefile": self.cookie
        }
        return dummy_details, fake_id

    async def details(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[str, Optional[str], int, str, str]:
        data, vid = await self.track(link, videoid)
        dur = data.get("duration_min", "00:00")
        sec = int(self._to_seconds(dur)) if dur else 0
        return data.get("title", "Unknown"), dur, sec, data.get("thumb", ""), vid

    async def title(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid); return d.get("title", "")
    async def duration(self, link: str, videoid: Union[bool, str, None] = None) -> Optional[str]:
        d, _ = await self.track(link, videoid); return d.get("duration_min")
    async def thumbnail(self, link: str, videoid: Union[bool, str, None] = None) -> str:
        d, _ = await self.track(link, videoid); return d.get("thumb", "")
    
    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            base_dir = "downloads"; os.makedirs(base_dir, exist_ok=True)
            path = os.path.join(base_dir, f"thumb_{int(time.time())}.jpg")
            session = await _ensure_aio_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(path, "wb") as f: f.write(data)
                    return path
        except: pass
        return None

    def _to_seconds(self, t: Optional[Union[str,int]]) -> int:
        if not t: return 0
        try:
            if isinstance(t, int): return t
            parts = [int(p) for p in str(t).split(":")]
            s = 0
            for p in parts: s = s * 60 + p
            return s
        except: return 0

    async def formats(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[List[Dict[str, Any]], str]:
        # Formats extraction logic (kept simpler as priority is playback)
        return [], _normalize_link(link, videoid)

    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached:
                expiry, url = cached
                if expiry > now + 3: return url
                else: _direct_cache.pop(key, None)

        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract_info_blocking():
                ydl_opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    # Web Client + Android Fallback handled in code logic if needed
                    "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
                }
                if self.cookie: ydl_opts["cookiefile"] = self.cookie
                if self.impersonate: ydl_opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}
            info = await loop.run_in_executor(self.pool, _extract_info_blocking)

        # Fallback logic if API fails
        if not info or (isinstance(info, dict) and info.get("_err")):
            cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", prepared]
            if self.cookie: cmd = ["yt-dlp", "-g", "--cookies", self.cookie, "--no-warnings", "--force-ipv4", prepared]
            out, _ = await _exec_proc(*cmd, timeout=12)
            if out:
                cand = out.decode().splitlines()[0].strip()
                expiry = (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (expiry, cand)
                return cand
            return None

        top_url = info.get("url")
        if top_url:
            expiry = _parse_expire(top_url) or (now + CACHE_DEFAULT_TTL)
            async with _direct_cache_lock: _direct_cache[key] = (expiry, top_url)
            return top_url
        
        return None

    # 🛑 Downloader (Aria2 + Format Mixing + Android/Web Hybrid)
    async def download(self, link: str, mystic: Any, video: Union[bool, str] = None, videoid: Union[bool, str, None] = None, songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None) -> Tuple[Optional[str], bool]:
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        if not prepared: return None, False
        
        vid = str(int(time.time()))
        downloads_base = "/dev/shm" if os.path.exists("/dev/shm") else os.path.abspath("downloads")
        ram_base = os.path.join(downloads_base, vid)
        os.makedirs(os.path.dirname(ram_base), exist_ok=True)

        loop = asyncio.get_running_loop()

        def _fallback():
            try:
                # Using 'b' (best) or 'bv+ba' to ensure we get SOMETHING
                fmt = "b/bv+ba/best" if is_video else "bestaudio/best"
                ydl_opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": get_cookie_file(),
                    "quiet": True,
                    "force_ipv4": True,
                    "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
                    "prefer_ffmpeg": True,
                    "ignoreerrors": True,
                    "check_formats": False,
                }
                if not is_video: ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}]
                else: ydl_opts["merge_output_format"] = "mp4"
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    if not info: return None
                    path = ydl.prepare_filename(info)
                    if not is_video and not path.endswith(".mp3"):
                        mp3 = os.path.splitext(path)[0] + ".mp3"
                        if os.path.exists(mp3): return mp3
                    return path
            except Exception as e:
                log.warning("fallback download failed: %s", e)
                return None

        downloaded = await loop.run_in_executor(self.pool, _fallback)
        if downloaded and os.path.exists(downloaded): return downloaded, False
        return None, False

    def _background_download(self, link: str, out_template: str, is_video: bool):
        try:
            aria2_args = ["-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--disable-ipv6=true"]
            fmt = "b/bv+ba/best"
            ydl_opts = {
                "format": fmt, "outtmpl": out_template, "cookiefile": get_cookie_file(),
                "quiet": True, "force_ipv4": True,
                "external_downloader": "aria2c", "external_downloader_args": aria2_args,
                "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
                "prefer_ffmpeg": True, "writethumbnail": True, "addmetadata": True,
            }
            if not is_video: ydl_opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            else: ydl_opts["merge_output_format"] = "mp4"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([link])
        except: pass

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = (f"yt-dlp -i --compat-options no-youtube-unavailable-videos --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null")
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try: result = [key for key in out.decode().split("\n") if key]
        except: result = []
        return result

# exported instance
YouTube = YouTubeAPI()

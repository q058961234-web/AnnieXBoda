# file: AnnieXMedia/platforms/Youtube.py
# 🚀 H200 Hybrid Engine (2026) - Fixed URL Attribute Error
# Merged Features:
# 1. Ultra-Fast Metadata via 'py-yt-search' (Instant Track/Search).
# 2. Robust Stream Extraction via 'yt-dlp' (Native/Aria2 Support).
# 3. Smart Caching & RAM Disk Optimization.

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

# 🔥 Smart Import: py-yt-search for Speed
try:
    from py_yt import VideosSearch
    PY_YT_AVAILABLE = True
except ImportError:
    PY_YT_AVAILABLE = False

# ⚡ Fast JSON Parser
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
except Exception:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))

# 🎛️ Configuration (H200 Optimized)
log = logging.getLogger("AnnieXMedia.YouTube")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)
log.setLevel(logging.INFO)

MAX_YTDLP_THREADS = 32  # Unleash H200 Cores
MAX_CONCURRENT_EXTRACTS = 10
YTDLP_SOCKET_TIMEOUT = 10
PROBE_TIMEOUT = 1.5
CACHE_DEFAULT_TTL = 600
AIO_CONN_LIMIT = 100
META_CACHE_TTL = 3600

# Pools & Locks
_thread_pool = ThreadPoolExecutor(max_workers=MAX_YTDLP_THREADS)
_extract_sema = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTS)

# 🌐 High-Performance Networking
_aio_connector = aiohttp.TCPConnector(limit=AIO_CONN_LIMIT, ssl=False, keepalive_timeout=300)
_aio_session: Optional[aiohttp.ClientSession] = None

# Caches
_direct_cache: Dict[str, Tuple[int, str]] = {}
_direct_cache_lock = asyncio.Lock()
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_meta_cache_lock = asyncio.Lock()

# 🍪 Cookies
COOKIE_PATHS = [
    "AnnieXMedia/assets/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
    "assets/cookies.txt",
    "/app/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return os.path.abspath(p)
        except: continue
    return None

async def _ensure_aio_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(connector=_aio_connector, raise_for_status=False)
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out, err
    except asyncio.TimeoutError:
        return b"", b"timeout"
    except:
        return b"", b"error"

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    try:
        if isinstance(videoid, str) and re.match(r'^[0-9A-Za-z_-]{11}$', videoid):
            return "https://www.youtube.com/watch?v=" + videoid
    except: pass
    if not link: return ""
    link = link.strip()
    if "youtu.be/" in link:
        return "https://www.youtube.com/watch?v=" + link.split("/")[-1].split("?")[0]
    return link.split("&")[0]

def _parse_expire(url: str) -> Optional[int]:
    try:
        params = parse_qs(urlparse(url).query)
        if "expire" in params: return int(params["expire"][0])
    except: pass
    return None

async def _probe_url(url: str, timeout: float = PROBE_TIMEOUT) -> Tuple[bool, Optional[str]]:
    try:
        sess = await _ensure_aio_session()
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnnieXMedia/1.0)"}
        try:
            async with sess.head(url, headers=headers, timeout=timeout) as r:
                if r.status < 400: return True, r.headers.get("Content-Type")
        except:
            try:
                async with sess.get(url, headers={**headers, "Range": "bytes=0-1023"}, timeout=timeout) as r2:
                    if r2.status in (200, 206): return True, r2.headers.get("Content-Type")
            except: return False, None
    except: return False, None
    return False, None

def _score_format(fmt: dict, prefer_audio: bool) -> int:
    score = 0
    proto = (fmt.get("protocol") or "").lower()
    ext = (fmt.get("ext") or "").lower()
    vcodec = fmt.get("vcodec") or ""
    acodec = fmt.get("acodec") or ""
    if proto.startswith("https"): score += 30
    if vcodec != "none" and acodec != "none": score += 50
    if prefer_audio and acodec != "none": score += 15
    if ext == "mp4": score += 10
    return score

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
        except:
            self.impersonate = False

    # 🛑 الدالة التي كانت مفقودة (تمت إعادتها لإصلاح الـ Error)
    async def url(self, message) -> Optional[str]:
        """Extract URL from a pyrogram Message-like object."""
        if not message: return None
        msgs = [message]
        if getattr(message, "reply_to_message", None): msgs.append(message.reply_to_message)
        for msg in msgs:
            text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
            entities = (getattr(msg, "entities", None) or []) + (getattr(msg, "caption_entities", None) or [])
            for ent in entities:
                try:
                    if getattr(ent, "url", None): return ent.url.split("&si")[0]
                    # Handle Text Links logic
                    t = str(getattr(ent, "type", ""))
                    if "URL" in t or "url" in t: 
                        off = getattr(ent, "offset", 0)
                        ln = getattr(ent, "length", 0)
                        return text[off:off+ln].split("&si")[0]
                except: pass
        return None

    # --- Cache Utils ---
    async def invalidate_direct_cache(self, vid_or_link: Optional[str]) -> None:
        if not vid_or_link: return
        try:
            async with _direct_cache_lock:
                keys = list(_direct_cache.keys())
                for k in keys:
                    if vid_or_link in k: _direct_cache.pop(k, None)
        except: pass

    async def clear_direct_cache(self) -> None:
        try:
            async with _direct_cache_lock: _direct_cache.clear()
        except: pass

    # --- Search Engine (Hybrid) ---
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        # 🚀 1. Try Ultra-Fast py_yt
        if PY_YT_AVAILABLE:
            try:
                v_search = VideosSearch(query, limit=limit)
                res = await v_search.next()
                if res and "result" in res:
                    return [{
                        "title": x.get("title", "Unknown"),
                        "vidid": x.get("id", ""),
                        "duration": x.get("duration", "")
                    } for x in res["result"]]
            except Exception as e:
                log.debug(f"py_yt search failed: {e}")

        # 🐢 2. Fallback to yt-dlp
        cmd = ["yt-dlp", "--dump-json", f"ytsearch{limit}:{query}", "--flat-playlist", "--no-warnings", "--skip-download"]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd, timeout=12)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    data = _loads_bytes(line.encode())
                    results.append({
                        "title": data.get("title", "Unknown"),
                        "vidid": data.get("id", ""),
                        "duration": data.get("duration_string", "")
                    })
                except: pass
        return results

    # --- Metadata Engine (Hybrid) ---
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        prepared = _normalize_link(link, videoid)
        key = "q:" + (prepared or "")
        now = time.time()

        async with _meta_cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if now - ts < META_CACHE_TTL: return data, vid

        # 🚀 1. Try Ultra-Fast py_yt for Metadata
        if PY_YT_AVAILABLE:
            try:
                v_search = VideosSearch(prepared, limit=1)
                res = await v_search.next()
                if res and res.get("result"):
                    data = res["result"][0]
                    thumb = (data.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]
                    details = {
                        "title": data.get("title", ""),
                        "link": data.get("link", prepared),
                        "vidid": data.get("id", ""),
                        "duration_min": data.get("duration"),
                        "thumb": thumb,
                        "cookiefile": self.cookie,
                    }
                    async with _meta_cache_lock: _meta_cache[key] = (now, details, data.get("id", ""))
                    return details, data.get("id", "")
            except: pass

        # 🐢 2. Fallback to yt-dlp
        cmd = ["yt-dlp", "--dump-json", prepared, "--no-warnings", "--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, err = await _exec_proc(*cmd, timeout=14)
        if out:
            try:
                info = _loads_bytes(out)
                thumb = (info.get("thumbnail") or "").split("?")[0]
                details = {
                    "title": info.get("title", "") or "",
                    "link": info.get("webpage_url", prepared),
                    "vidid": info.get("id", ""),
                    "duration_min": info.get("duration"),
                    "thumb": thumb,
                    "cookiefile": self.cookie,
                }
                async with _meta_cache_lock: _meta_cache[key] = (now, details, info.get("id", ""))
                return details, info.get("id", "")
            except: pass
        
        return {"title": "Unknown", "link": prepared, "vidid": "", "thumb": ""}, ""

    # --- Direct Link (Stream) Engine ---
    async def get_direct_link(self, link: str, *, prefer_audio: bool = True) -> Optional[str]:
        prepared = _normalize_link(link)
        if not prepared: return None
        key = prepared + ("::audio" if prefer_audio else "::video")
        now = int(time.time())

        # 1. Cache Check
        async with _direct_cache_lock:
            cached = _direct_cache.get(key)
            if cached and cached[0] > now + 3: return cached[1]

        # 2. Extract with ThreadPool
        async with self.sema:
            loop = asyncio.get_running_loop()
            def _extract():
                opts = {
                    "quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                    "socket_timeout": YTDLP_SOCKET_TIMEOUT,
                    "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}}, # Mobile clients are faster
                }
                if self.cookie: opts["cookiefile"] = self.cookie
                if self.impersonate: opts["impersonate"] = "chrome"
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(prepared, download=False)
                except Exception as e: return {"_err": str(e)}
            
            info = await loop.run_in_executor(self.pool, _extract)

        # 3. Analyze Results
        if not info or info.get("_err"):
            # Fallback -g (Last Resort)
            cmd = ["yt-dlp", "-g", "--no-warnings", "--force-ipv4", prepared]
            if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
            out, _ = await _exec_proc(*cmd)
            if out:
                cand = out.decode().splitlines()[0].strip()
                ok, _ = await _probe_url(cand)
                if ok:
                    exp = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                    async with _direct_cache_lock: _direct_cache[key] = (exp - 3, cand)
                    return cand
            return None

        # 4. Score Formats
        fmts = info.get("formats", [])
        candidates = []
        for f in fmts:
            url = f.get("url")
            if not url: continue
            proto = f.get("protocol", "").lower()
            if not proto.startswith(("http", "https", "m3u8")): continue
            
            if prefer_audio and f.get("acodec") == "none": continue
            if not prefer_audio and f.get("vcodec") != "none" and f.get("acodec") != "none":
                candidates.append((_score_format(f, prefer_audio), url)); continue
            if f.get("acodec") != "none":
                candidates.append((_score_format(f, prefer_audio), url))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # 5. Probe Candidates
        for _, cand in candidates[:5]:
            ok, _ = await _probe_url(cand)
            if ok:
                exp = _parse_expire(cand) or (now + CACHE_DEFAULT_TTL)
                async with _direct_cache_lock: _direct_cache[key] = (exp - 3, cand)
                return cand
        
        return None

    # --- Download Engine (RAM Disk + Background) ---
    async def download(
        self,
        link: str,
        mystic: Any,
        video: Union[bool, str] = None,
        videoid: Union[bool, str, None] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        is_video = bool(video or songvideo)
        prepared = _normalize_link(link, videoid)
        
        # Determine Path (RAM Disk for Speed)
        vid_id = str(int(time.time()))
        if videoid and len(videoid) == 11: vid_id = videoid
        
        downloads_base = "/dev/shm/AnnieDownloads" if os.path.exists("/dev/shm") else "downloads"
        os.makedirs(downloads_base, exist_ok=True)
        ram_base = os.path.join(downloads_base, vid_id)

        # 1. RAM Cache Check
        for ext in (".mp4", ".m4a", ".mp3", ".webm"):
            cand = f"{ram_base}{ext}"
            if os.path.exists(cand) and os.path.getsize(cand) > 1024:
                return cand, False

        loop = asyncio.get_running_loop()

        # 2. Try Direct Link First (Fast Stream)
        if not format_id:
            try:
                direct = await self.get_direct_link(prepared, prefer_audio=not is_video)
                if direct:
                    # Schedule background download to cache it for later
                    loop.run_in_executor(self.pool, lambda: self._background_download(prepared, f"{ram_base}.%(ext)s", is_video))
                    return direct, True
            except: pass

        # 3. Fallback: Force Download
        def _dl():
            try:
                fmt = "best[ext=mp4]/best" if is_video else "bestaudio[ext=m4a]/bestaudio/best"
                opts = {
                    "format": fmt,
                    "outtmpl": f"{ram_base}.%(ext)s",
                    "cookiefile": self.cookie,
                    "quiet": True,
                    "force_ipv4": True,
                    # Native H200 Speed (No external Aria2 needed)
                    "concurrent_fragment_downloads": 16,
                    "buffersize": 1024 * 1024,
                }
                if not is_video:
                    opts["postprocessors"] = [{"key": "FFmpegExtractAudio","preferredcodec": "mp3","preferredquality": "192"}]
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(prepared, download=True)
                    path = ydl.prepare_filename(info)
                    if not is_video: path = os.path.splitext(path)[0] + ".mp3"
                    return path
            except Exception as e:
                log.warning(f"DL Fail: {e}")
                return None

        path = await loop.run_in_executor(self.pool, _dl)
        return path, False

    def _background_download(self, link, out_tmpl, is_video):
        """Background downloader to cache popular songs without blocking."""
        try:
            # Try to use Aria2 if available for background tasks
            aria_args = ["-x", "16", "-s", "16", "-k", "1M"]
            opts = {
                "format": "bestaudio/best",
                "outtmpl": out_tmpl,
                "cookiefile": self.cookie,
                "quiet": True,
                "external_downloader": "aria2c",
                "external_downloader_args": aria_args
            }
            if is_video: opts["format"] = "bestvideo+bestaudio/best"
            else: opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([link])
        except: pass

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        try:
            path = f"/dev/shm/thumb_{int(time.time())}.jpg"
            sess = await _ensure_aio_session()
            async with sess.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f: f.write(await resp.read())
                    return path
        except: pass
        return None

    # --- Wrappers ---
    async def playlist(self, link, limit, **kwargs):
        prepared = _normalize_link(link, kwargs.get("videoid"))
        cmd = f"yt-dlp --get-id --flat-playlist --playlist-end {limit} --skip-download '{prepared}'"
        out, _ = await _exec_proc(cmd, shell=True)
        return [x for x in out.decode().split("\n") if x]

    async def details(self, link, videoid=None):
        d, vid = await self.track(link, videoid)
        return d.get("title"), d.get("duration_min"), 0, d.get("thumb"), vid

    async def title(self, link, videoid=None):
        d, _ = await self.track(link, videoid); return d.get("title", "")

    async def thumbnail(self, link, videoid=None):
        d, _ = await self.track(link, videoid); return d.get("thumb", "")

    async def duration(self, link, videoid=None):
        d, _ = await self.track(link, videoid); return d.get("duration_min")

# Export Instance
YouTube = YouTubeAPI()

# file: AnnieXMedia/platforms/Youtube.py
# 🚀 H200 Native Speed Edition (2026) - The "Flash" Version
# Features:
# 1. Native Multi-Threading (No Aria2 needed).
# 2. Instant Live Stream Extraction (HLS Low Latency).
# 3. RAM Disk Processing (/dev/shm).
# 4. Full Class Coverage (No Crashes).

import asyncio
import logging
import os
import time
import re
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

import aiohttp
import yt_dlp

# ⚡ 2026: Ultra-Fast JSON Parser (Fallbacks included)
try:
    import orjson as _orjson
    def _loads_bytes(b: bytes): return _orjson.loads(b)
    def _dumps_bytes(o: Any): return _orjson.dumps(o)
except ImportError:
    def _loads_bytes(b: bytes): return json.loads(b.decode("utf-8", "ignore"))
    def _dumps_bytes(o: Any): return json.dumps(o).encode()

# 🎛️ Configuration
log = logging.getLogger("AnnieX_YouTube_Native")
MAX_WORKERS = 64  # Unleash H200 Cores
RAM_DISK = "/dev/shm/AnnieDownloads"

# Thread Pool for blocking operations
_thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_extract_sema = asyncio.Semaphore(50) # Allow high concurrency

# 🌐 High-Performance Networking (Keep-Alive)
_aio_connector = aiohttp.TCPConnector(
    limit=1000,
    ttl_dns_cache=300,
    use_dns_cache=True,
    ssl=False,
    keepalive_timeout=120
)
_aio_session: Optional[aiohttp.ClientSession] = None

# 🧠 Smart Caching
_direct_cache: Dict[str, Tuple[int, str]] = {}
_meta_cache: Dict[str, Tuple[float, Dict[str, Any], str]] = {}
_cache_lock = asyncio.Lock()

# 🍪 Cookies Management
COOKIE_PATHS = [
    "/app/cookies.txt",
    "cookies.txt",
    "AnnieXMedia/cookies.txt",
]

def get_cookie_file() -> Optional[str]:
    for p in COOKIE_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return os.path.abspath(p)
    return None

async def _ensure_session() -> aiohttp.ClientSession:
    global _aio_session
    if _aio_session is None or _aio_session.closed:
        _aio_session = aiohttp.ClientSession(
            connector=_aio_connector,
            json_serialize=_dumps_bytes
        )
    return _aio_session

async def _exec_proc(*args: str, timeout: int = 10) -> Tuple[bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except: return b"", b""

def _normalize_link(link: str, videoid: Union[bool, str, None] = None) -> str:
    if videoid and isinstance(videoid, str) and len(videoid) == 11:
        return f"https://www.youtube.com/watch?v={videoid}"
    if "youtu.be/" in link:
        return f"https://www.youtube.com/watch?v={link.split('youtu.be/')[1].split('?')[0]}"
    return link.split("&")[0]

class YouTubeAPI:
    def __init__(self):
        self.pool = _thread_pool
        self.cookie = get_cookie_file()
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        if not os.path.exists(RAM_DISK):
            os.makedirs(RAM_DISK, exist_ok=True)

    # ---------------------------------------------------
    # 🔍 Search (Optimized & Fast)
    # ---------------------------------------------------
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """Returns search results quickly using yt-dlp flat playlist."""
        cmd = [
            "yt-dlp", "--dump-json", f"ytsearch{limit}:{query}",
            "--flat-playlist", "--no-warnings", "--skip-download"
        ]
        if self.cookie: cmd[1:1] = ["--cookies", self.cookie]
        
        out, _ = await _exec_proc(*cmd, timeout=8)
        results = []
        if out:
            for line in out.decode().splitlines():
                try:
                    d = _loads_bytes(line.encode())
                    results.append({
                        "title": d.get("title", "Unknown"),
                        "vidid": d.get("id", ""),
                        "duration": d.get("duration_string", "00:00")
                    })
                except: pass
        return results

    # ---------------------------------------------------
    # ℹ️ Metadata Tracking (Cached)
    # ---------------------------------------------------
    async def track(self, link: str, videoid: Union[bool, str, None] = None) -> Tuple[Dict[str, Any], str]:
        url = _normalize_link(link, videoid)
        key = f"meta:{url}"
        
        async with _cache_lock:
            if key in _meta_cache:
                ts, data, vid = _meta_cache[key]
                if time.time() - ts < 3600: return data, vid

        loop = asyncio.get_running_loop()
        def _extract():
            # Android API is fastest for metadata lookup
            opts = {
                "quiet": True,
                "dump_single_json": True,
                "skip_download": True,
                "cookiefile": self.cookie,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await loop.run_in_executor(self.pool, _extract)
            details = {
                "title": info.get("title", ""),
                "link": info.get("webpage_url", url),
                "vidid": info.get("id", ""),
                "duration_min": info.get("duration"),
                "thumb": (info.get("thumbnail") or "").split("?")[0],
                "is_live": info.get("is_live", False)
            }
            async with _cache_lock:
                _meta_cache[key] = (time.time(), details, info.get("id"))
            return details, info.get("id")
        except Exception as e:
            log.error(f"Track Failed: {e}")
            return {"title": "Unknown"}, ""

    # ---------------------------------------------------
    # ⚡ Get Direct Link (The "Turbo" Method)
    # ---------------------------------------------------
    async def get_direct_link(self, link: str, prefer_audio: bool = True) -> Optional[str]:
        url = _normalize_link(link)
        key = f"direct:{url}:{prefer_audio}"
        
        # 1. Check Cache
        async with _cache_lock:
            if key in _direct_cache:
                exp, dlink = _direct_cache[key]
                if exp > time.time(): return dlink

        loop = asyncio.get_running_loop()

        def _get_link():
            # 🚀 Strategy: Prioritize iOS/Android clients for speed and skip DASH for audio
            opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best" if prefer_audio else "bestvideo+bestaudio/best",
                "cookiefile": self.cookie,
                "socket_timeout": 5,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["ios", "android", "web"], # Client rotation
                        "skip": ["dash"] if prefer_audio else [] 
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # 🔥 LIVE STREAM INSTANT FIX
                if info.get("is_live") or info.get("was_live"):
                    # Always prefer HLS (m3u8) for live streams (Instant Play)
                    if "url" in info and ".m3u8" in info["url"]:
                        return info["url"]
                    # Search in formats
                    for f in info.get("formats", []):
                        if ".m3u8" in f.get("url", ""):
                            return f["url"]
                
                return info.get("url")

        try:
            async with _extract_sema:
                direct_url = await loop.run_in_executor(self.pool, _get_link)
            
            if direct_url:
                # Cache Logic: Store for 3 hours unless expired
                expire_time = time.time() + 10800
                if "expire=" in direct_url:
                    try: 
                        val = int(direct_url.split("expire=")[1].split("&")[0])
                        # If val is huge, it's epoch, else it's seconds
                        expire_time = val if val > 1000000000 else time.time() + val
                    except: pass
                
                async with _cache_lock:
                    _direct_cache[key] = (expire_time, direct_url)
                return direct_url
        except Exception:
            pass
        return None

    # ---------------------------------------------------
    # 🔥 Native Multi-Threaded Download (No Aria2)
    # ---------------------------------------------------
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
        url = _normalize_link(link, videoid)
        
        # Determine RAM paths
        vid_id = videoid if videoid and len(videoid) == 11 else str(int(time.time()))
        out_tmpl = f"{RAM_DISK}/{vid_id}.%(ext)s"
        cached_file = f"{RAM_DISK}/{vid_id}.{'mp4' if is_video else 'mp3'}"
        
        # Check Cache
        if os.path.exists(cached_file): return cached_file, False

        # Try Direct Link for Stream-Only (Save Bandwidth)
        if not format_id:
            dlink = await self.get_direct_link(url, prefer_audio=not is_video)
            if dlink: return dlink, True

        loop = asyncio.get_running_loop()

        def _native_download():
            # 🚀 NATIVE SPEED CONFIGURATION (The Secret Sauce)
            opts = {
                "quiet": True,
                "outtmpl": out_tmpl,
                "cookiefile": self.cookie,
                
                # ✅ ENABLE NATIVE MULTI-THREADING (32 Threads!)
                "concurrent_fragment_downloads": 32, 
                "buffersize": 1024 * 1024, # 1MB Buffer
                "http_chunk_size": 10485760, # 10MB Chunks
                
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]" if is_video else "bestaudio[ext=m4a]/bestaudio/best",
                "writethumbnail": False,
                "overwrites": True,
                
                # Faster Post-Processing
                "postprocessors": [{
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4"
                }] if is_video else [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }],
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        try:
            fpath = await loop.run_in_executor(self.pool, _native_download)
            
            # Extension Fixer
            if not is_video and fpath and not fpath.endswith(".mp3"):
                mp3_path = os.path.splitext(fpath)[0] + ".mp3"
                if os.path.exists(mp3_path): return mp3_path, False
            
            if fpath and os.path.exists(fpath): return fpath, False
            
        except Exception as e:
            log.error(f"Download Error: {e}")
        
        return None, False

    async def download_thumb(self, url: str) -> Optional[str]:
        if not url: return None
        path = f"{RAM_DISK}/thumb_{int(time.time())}.jpg"
        try:
            sess = await _ensure_session()
            async with sess.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        f.write(await resp.read())
                    return path
        except: pass
        return None

    # ---------------------------------------------------
    # 📜 Playlist & Helper Support (Completeness)
    # ---------------------------------------------------
    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        
        cmd = (
            f"yt-dlp -i --compat-options no-youtube-unavailable-videos "
            f"--get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' "
            f"2>/dev/null"
        )
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        try:
            return [key for key in out.decode().split("\n") if key]
        except: return []

    async def details(self, link: str, videoid=None):
        d, vid = await self.track(link, videoid)
        return d.get("title"), d.get("duration_min"), 0, d.get("thumb"), vid

    async def title(self, link: str, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("title", "")
        
    async def duration(self, link: str, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("duration_min")

    async def thumbnail(self, link: str, videoid=None):
        d, _ = await self.track(link, videoid)
        return d.get("thumb")

# Export Instance
YouTube = YouTubeAPI()

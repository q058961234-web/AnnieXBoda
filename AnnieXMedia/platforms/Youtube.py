# Authored By Certified Coders © 2026
# H200 ULTIMATE: py_yt (Metadata) + yt-dlp (H200 NVENC)
# Features: Async Search via py_yt, Anti-Ban Android Client, Universal Format Fix.

import asyncio
import os
import re
import logging
from typing import Union, Optional, Tuple, List, Dict

from yt_dlp import YoutubeDL
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
# 🔥 المكتبة الجديدة
from py_yt import VideosSearch

import config

log = logging.getLogger("AnnieXMedia.YouTube")

def cookiefile():
    possible_paths = [
        "cookies/cookies.txt", 
        "cookies.txt", 
        "AnnieXMedia/cookies.txt", 
        "AnnieXMedia/assets/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path): return path
    return None

def time_to_seconds(time):
    try:
        parts = str(time).split(":")
        return sum(int(x) * 60**i for i, x in enumerate(reversed(parts)))
    except: return 0

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
        text = ""
        offset, length = None, None
        for message in messages:
            if offset: break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK: return entity.url
        return None if offset in (None,) else text[offset : offset + length]

    # ==================================================================
    # ⚡ NEW: Ultra-Fast Search via py_yt
    # ==================================================================
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        query = link.split("&")[0] if "&" in link else link
        
        try:
            # استخدام py_yt للبحث السريع
            search = VideosSearch(query, limit=1)
            res = await search.next()
            if not res or not res.get("result"): 
                return "Unknown", "00:00", 0, "", ""
            
            result = res["result"][0]
            title = result.get("title", "Unknown")
            duration_min = result.get("duration", "00:00")
            
            # معالجة الصور المصغرة
            thumbnails = result.get("thumbnails", [])
            thumbnail = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
            
            vidid = result.get("id", "")
            duration_sec = int(time_to_seconds(duration_min))
            
            return title, duration_min, duration_sec, thumbnail, vidid
        except Exception as e:
            log.error(f"py_yt Details Error: {e}")
            return "Unknown", "00:00", 0, "", ""

    # ==================================================================
    # 🚀 DIRECT LINK (H200 + Android Client)
    # ==================================================================
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        cmd = [
            "yt-dlp", "-g", "--no-warnings", "--quiet", "--force-ipv4",
            "--no-check-certificate",
            # Android Client لتجنب الحظر
            "--extractor-args", "youtube:player_client=android",
            # قبول أي صيغة لتجنب خطأ Format Not Available
            "-f", "best/bestvideo+bestaudio", 
            f"{link}"
        ]

        if cookiefile():
            cmd.insert(1, "--cookies")
            cmd.insert(2, cookiefile())

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        return 0, stderr.decode()

    async def get_direct_link(self, link: str, prefer_audio: bool = True) -> Optional[str]:
        status, url = await self.video(link)
        return url if status == 1 else None

    # ==================================================================
    # 📥 DOWNLOADER (Aria2 Optimized)
    # ==================================================================
    async def download(
        self, link: str, mystic, video: bool = None, videoid: str = None, 
        songaudio: bool = None, songvideo: bool = None, format_id: str = None, title: str = None
    ) -> Tuple[Optional[str], bool]:
        
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()

        base_opts = {
            "cookiefile": cookiefile(), "quiet": True, "no_warnings": True,
            "external_downloader": "aria2c",
            "external_downloader_args": ["-x", "16", "-k", "1M", "-s", "16"],
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "nocheckcertificate": True,
            "check_formats": False,
        }

        def audio_dl():
            opts = base_opts.copy()
            opts.update({
                "format": "bestaudio/best", 
                "outtmpl": "downloads/%(id)s.%(ext)s", 
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            })
            with YoutubeDL(opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.mp3")
                if os.path.exists(xyz): return xyz
                x.download([link]); return xyz

        def video_dl():
            opts = base_opts.copy()
            opts.update({
                "format": "bestvideo+bestaudio/best", 
                "outtmpl": "downloads/%(id)s.%(ext)s", 
                "merge_output_format": "mp4"
            })
            with YoutubeDL(opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.mp4")
                if os.path.exists(xyz): return xyz
                x.download([link]); return xyz

        try:
            if songvideo:
                fpath = f"downloads/{title}.mp4"
                opts = base_opts.copy()
                opts.update({"format": f"{format_id}+bestaudio/best", "outtmpl": fpath, "merge_output_format": "mp4"})
                await loop.run_in_executor(None, lambda: YoutubeDL(opts).download([link]))
                return fpath, False
            elif songaudio:
                fpath = f"downloads/{title}.mp3"
                opts = base_opts.copy()
                opts.update({"format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
                await loop.run_in_executor(None, lambda: YoutubeDL(opts).download([link]))
                return fpath, False
            elif video:
                dl = await loop.run_in_executor(None, video_dl)
                return dl, False
            else:
                dl = await loop.run_in_executor(None, audio_dl)
                return dl, True
        except Exception as e:
            log.error(f"Download Error: {e}")
            return None, False

    # ==================================================================
    # 🛠️ HELPERS (py_yt Powered)
    # ==================================================================
    async def search(self, query: str, limit: int = 10):
        try:
            search = VideosSearch(query, limit=limit)
            res = await search.next()
            if not res or not res.get("result"): return []
            return [{"title": x.get("title"), "vidid": x.get("id"), "duration": x.get("duration")} for x in res["result"]]
        except: return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            search = VideosSearch(link, limit=1)
            res = await search.next()
            if not res or not res.get("result"): raise Exception("Not found")
            result = res["result"][0]
            
            # التعامل مع الصور بجودة عالية
            thumbnails = result.get("thumbnails", [])
            thumb = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
            
            return {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": thumb,
                "cookiefile": cookiefile()
            }, result["id"]
        except: return {}, ""

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            search = VideosSearch(link, limit=10)
            res = await search.next()
            if not res or not res.get("result"): return "Unknown", "00:00", "", ""
            
            results = res["result"]
            idx = query_type if query_type < len(results) else 0
            
            thumbnails = results[idx].get("thumbnails", [])
            thumb = thumbnails[0]["url"].split("?")[0] if thumbnails else ""
            
            return results[idx]["title"], results[idx]["duration"], thumb, results[idx]["id"]
        except: return "Unknown", "00:00", "", ""

    async def playlist(self, link, limit, user_id=None, videoid: Union[bool, str] = None):
        # yt-dlp هو الأسرع والأضمن لجلب الروابط الداخلية للقوائم المسطحة
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        cmd = f"yt-dlp -i --flat-playlist --print id --playlist-end {limit} --skip-download '{link}'"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [x for x in out.decode().split("\n") if x]

    async def download_thumb(self, url): return url
    async def title(self, link: str): d, _ = await self.track(link); return d.get("title", "Unknown")
    async def duration(self, link: str): d, _ = await self.track(link); return d.get("duration_min", "00:00")
    async def thumbnail(self, link: str): d, _ = await self.track(link); return d.get("thumb", "")
    async def invalidate_direct_cache(self, vid_or_link): pass
    async def clear_direct_cache(self): pass

YouTube = YouTubeAPI()

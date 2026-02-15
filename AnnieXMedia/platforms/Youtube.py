# Authored By Certified Coders © 2026
# Optimized YouTube Module: Alexa's Speed + Annie's Stability
# Uses yt-dlp -g for instant links & youtubesearchpython for fast metadata.

import asyncio
import os
import re
import json
import logging
from typing import Union, List, Dict, Tuple, Optional

from yt_dlp import YoutubeDL
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.aio import VideosSearch

import config

# Logger
log = logging.getLogger("AnnieXMedia.YouTube")

def cookiefile():
    # يبحث عن ملف الكوكيز في عدة مسارات محتملة
    possible_paths = [
        "cookies/cookies.txt",
        "cookies.txt",
        "AnnieXMedia/cookies.txt",
        "AnnieXMedia/assets/cookies.txt"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None if offset in (None,) else text[offset : offset + length]

    # --- Fast Metadata using youtubesearchpython (Alexa Style) ---
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res["result"]:
                raise Exception("No results")
            result = res["result"][0]
            
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
            return title, duration_min, duration_sec, thumbnail, vidid
        except Exception as e:
            log.error(f"Error in details: {e}")
            return "Unknown", "00:00", 0, "", ""

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["title"] if res["result"] else "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["duration"] if res["result"] else "00:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["thumbnails"][0]["url"].split("?")[0] if res["result"] else ""

    # --- Fast Direct Link (The Core of Speed) ---
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        # استخدام subprocess لاستخراج الرابط المباشر بسرعة
        cmd = [
            "yt-dlp",
            "-g",
            "-f", "best[height<=?720][width<=?1280]",
            f"{link}"
        ]
        if cookiefile():
            cmd.insert(1, "--cookies")
            cmd.insert(2, cookiefile())

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    # Compatibility Wrapper for AnnieXMedia
    async def get_direct_link(self, link: str, prefer_audio: bool = True) -> Optional[str]:
        # نستخدم نفس منطق اليكسا للحصول على الرابط المباشر
        status, url = await self.video(link)
        if status == 1:
            return url
        return None

    # --- Playlist & Track Info ---
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        
        cmd = f"yt-dlp -i --compat-options no-youtube-unavailable-videos --get-id --flat-playlist --playlist-end {limit} --skip-download '{link}' 2>/dev/null"
        
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        try:
            result = [key for key in out.decode().split("\n") if key]
        except Exception:
            result = []
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        results = VideosSearch(link, limit=1)
        res = await results.next()
        if not res["result"]:
            raise Exception("Track not found")
            
        result = res["result"][0]
        title = result["title"]
        duration_min = result["duration"]
        vidid = result["id"]
        yturl = result["link"]
        thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
            "cookiefile": cookiefile(),
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        ytdl_opts = {"quiet": True}
        if cookiefile():
            ytdl_opts["cookiefile"] = cookiefile()
            
        ydl = YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            try:
                r = ydl.extract_info(link, download=False)
                for format in r.get("formats", []):
                    formats_available.append({
                        "format": format.get("format"),
                        "filesize": format.get("filesize"),
                        "format_id": format.get("format_id"),
                        "ext": format.get("ext"),
                        "format_note": format.get("format_note"),
                        "yturl": link,
                        "cookiefile": cookiefile(),
                    })
            except Exception:
                pass
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        a = VideosSearch(link, limit=10)
        res = await a.next()
        result = res.get("result", [])
        if not result:
            return "Unknown", "00:00", "", ""
            
        # Ensure query_type is within bounds
        idx = query_type if query_type < len(result) else 0
        
        title = result[idx]["title"]
        duration_min = result[idx]["duration"]
        vidid = result[idx]["id"]
        thumbnail = result[idx]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid

    # --- Fast Download Logic (Alexa Style) ---
    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> Tuple[Optional[str], bool]:
        
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        def audio_dl():
            ydl_optssx = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            if cookiefile():
                ydl_optssx["cookiefile"] = cookiefile()
                
            with YoutubeDL(ydl_optssx) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz):
                    return xyz
                x.download([link])
                return xyz

        def video_dl():
            ydl_optssx = {
                "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            if cookiefile():
                ydl_optssx["cookiefile"] = cookiefile()
                
            with YoutubeDL(ydl_optssx) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if os.path.exists(xyz):
                    return xyz
                x.download([link])
                return xyz

        def song_dl(is_video=False):
            fpath = f"downloads/{title}"
            ydl_optssx = {
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "prefer_ffmpeg": True,
            }
            if cookiefile():
                ydl_optssx["cookiefile"] = cookiefile()

            if is_video:
                ydl_optssx["format"] = f"{format_id}+140"
                ydl_optssx["merge_output_format"] = "mp4"
            else:
                ydl_optssx["format"] = format_id
                ydl_optssx["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
                # Fix path extension for audio
                fpath = f"{fpath}.mp3" 
                ydl_optssx["outtmpl"] = f"downloads/{title}.%(ext)s"

            x = YoutubeDL(ydl_optssx)
            x.download([link])
            return fpath if is_video else f"downloads/{title}.mp3"

        # Execution Logic
        if songvideo:
            fpath = await loop.run_in_executor(None, lambda: song_dl(is_video=True))
            return fpath, False
        elif songaudio:
            fpath = await loop.run_in_executor(None, lambda: song_dl(is_video=False))
            return fpath, False
        
        # Streaming Logic
        if video:
            # Try Direct Link First (Fastest for Video)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]", f"{link}",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                if stdout:
                    return stdout.decode().split("\n")[0], True
            except Exception:
                pass
            # Fallback to download
            downloaded_file = await loop.run_in_executor(None, video_dl)
            return downloaded_file, False
        else:
            # Audio Stream -> Download is often safer for audio, but let's assume direct first if needed
            # For now, stick to Alexa's audio_dl (caching)
            downloaded_file = await loop.run_in_executor(None, audio_dl)
            return downloaded_file, True

    # --- Extra Methods to Prevent Crashes (Legacy Support) ---
    
    async def search(self, query: str, limit: int = 10):
        # استبدال البحث القديم بالبحث السريع
        try:
            results = VideosSearch(query, limit=limit)
            res = await results.next()
            return [{
                "title": x["title"],
                "vidid": x["id"],
                "duration": x["duration"]
            } for x in res["result"]]
        except Exception:
            return []

    async def download_thumb(self, url: str):
        # Helper to download thumbnail locally
        if not url: return None
        try:
            if not os.path.exists("downloads"):
                os.makedirs("downloads", exist_ok=True)
            path = f"downloads/thumb_{int(asyncio.get_event_loop().time())}.jpg"
            
            # Simple wget or curl or aiohttp could work, let's use yt-dlp internal or simple logic
            # For speed, let's use aiohttp if available, else skip
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        with open(path, "wb") as f:
                            f.write(data)
                        return path
        except:
            pass
        return None

    async def invalidate_direct_cache(self, vid_or_link):
        # Dummy function to prevent crash in Stream.py
        pass

    async def clear_direct_cache(self):
        # Dummy function
        pass

# Export Instance
YouTube = YouTubeAPI()

# Authored By Certified Coders © 2026
# H200 ULTIMATE: Correct Cookie Handling + Browser Impersonation
# Fixes: Cookie/Client Mismatch & Data Center IP Blocking

import asyncio
import os
import re
import logging
from typing import Union, Optional, Tuple

from yt_dlp import YoutubeDL
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

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
        if os.path.exists(path):
            return path
    return None

def time_to_seconds(time):
    try:
        stringt = str(time)
        return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))
    except:
        return 0

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
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
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
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None if offset in (None,) else text[offset : offset + length]

    # ==================================================================
    # ⚡ METADATA (YouTubSearchPython)
    # ==================================================================
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res["result"]: return "Unknown", "00:00", 0, "", ""
            result = res["result"][0]
            
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            duration_sec = 0 if str(duration_min) == "None" else int(time_to_seconds(duration_min))
            
            return title, duration_min, duration_sec, thumbnail, vidid
        except Exception as e:
            log.error(f"Metadata Error: {e}")
            return "Unknown", "00:00", 0, "", ""

    # ==================================================================
    # 🚀 DIRECT LINK (-g) WITH COOKIE COMPATIBILITY
    # ==================================================================
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        # الأساس: نستخدم الكوكيز
        cookie_path = cookiefile()
        
        cmd = [
            "yt-dlp",
            "-g",
            "--no-warnings",
            "--quiet",
            "--force-ipv4",
            "--no-check-certificate",
            # 👇 الحل لمشكلة التنسيق: أي جودة متاحة، لا تشترط MP4 الآن
            "-f", "best/bestvideo+bestaudio",
        ]

        if cookie_path:
            # ✅ الحالة 1: يوجد كوكيز
            # يجب استخدام Web Client ليطابق الكوكيز + Impersonate لخداع السيرفر
            cmd.extend([
                "--cookies", cookie_path,
                # هذا يحاكي متصفح حقيقي بالكامل لتمرير الكوكيز بنجاح
                "--impersonate", "chrome" 
            ])
        else:
            # ❌ الحالة 2: لا يوجد كوكيز
            # نلجأ للـ Android Client لتخطي الحظر
            cmd.extend([
                "--extractor-args", "youtube:player_client=android",
            ])

        cmd.append(f"{link}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        
        # ⚠️ Fallback: لو فشل بالكوكيز، جرب مرة تانية من غير كوكيز بوضع الأندرويد
        # (أحياناً الكوكيز تكون محروقة وتسبب الفشل)
        if cookie_path and stderr:
            log.warning("Cookies failed, retrying with Android Client...")
            fallback_cmd = [
                "yt-dlp", "-g", "--no-warnings", "--quiet", "--force-ipv4",
                "--extractor-args", "youtube:player_client=android",
                "-f", "best/bestvideo+bestaudio",
                f"{link}"
            ]
            proc_fb = await asyncio.create_subprocess_exec(
                *fallback_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_fb, err_fb = await proc_fb.communicate()
            if out_fb:
                return 1, out_fb.decode().split("\n")[0]
            return 0, err_fb.decode()

        return 0, stderr.decode()

    async def get_direct_link(self, link: str, prefer_audio: bool = True) -> Optional[str]:
        status, url = await self.video(link)
        return url if status == 1 else None

    # ==================================================================
    # 📥 DOWNLOADER (Aria2 + Smart Format)
    # ==================================================================
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
        
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        
        cookie_path = cookiefile()

        # إعدادات Aria2
        base_opts = {
            "quiet": True,
            "no_warnings": True,
            "external_downloader": "aria2c",
            "external_downloader_args": ["-x", "16", "-k", "1M", "-s", "16"],
            "nocheckcertificate": True,
            "check_formats": False, # سرعة
        }

        # ضبط العميل بناءً على وجود الكوكيز
        if cookie_path:
            base_opts["cookiefile"] = cookie_path
            # مهم جداً: لا نضع extractor_args هنا لأن الكوكيز تحتاج Web Client افتراضي
            # لكن يمكن تفعيل impersonate إذا كانت نسخة yt-dlp تدعمها عبر الـ API (غالبا تتطلب CLI)
            # لذا نعتمد على الكوكيز فقط هنا
        else:
            # بدون كوكيز -> أندرويد
            base_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}

        def audio_dl():
            opts = base_opts.copy()
            opts.update({
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
            with YoutubeDL(opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.mp3")
                if os.path.exists(xyz): return xyz
                x.download([link])
                return xyz

        def video_dl():
            opts = base_opts.copy()
            # 🔥 دمج التنسيقات (الحل لمشكلة requested format)
            opts.update({
                "format": "bestvideo+bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "merge_output_format": "mp4",
            })
            with YoutubeDL(opts) as x:
                info = x.extract_info(link, False)
                xyz = os.path.join("downloads", f"{info['id']}.mp4")
                if os.path.exists(xyz): return xyz
                x.download([link])
                return xyz

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
                opts.update({
                    "format": format_id, 
                    "outtmpl": f"downloads/{title}.%(ext)s",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                })
                await loop.run_in_executor(None, lambda: YoutubeDL(opts).download([link]))
                return fpath, False
            
            elif video:
                dl = await loop.run_in_executor(None, video_dl)
                return dl, False
            else:
                dl = await loop.run_in_executor(None, audio_dl)
                return dl, True
                
        except Exception as e:
            log.error(f"Download Failed: {e}")
            return None, False

    # ==================================================================
    # 🛠️ HELPER METHODS
    # ==================================================================
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        # استخدام subprocess لاستخراج القائمة
        cmd = ["yt-dlp", "-i", "--flat-playlist", "--print", "id", "--playlist-end", str(limit), "--skip-download", link]
        if cookiefile():
            cmd.insert(1, "--cookies")
            cmd.insert(2, cookiefile())
            
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [x for x in out.decode().split("\n") if x]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            results = VideosSearch(link, limit=1)
            res = await results.next()
            if not res["result"]: raise Exception("Track not found")
            result = res["result"][0]
            return {
                "title": result["title"],
                "link": result["link"],
                "vidid": result["id"],
                "duration_min": result["duration"],
                "thumb": result["thumbnails"][0]["url"].split("?")[0],
                "cookiefile": cookiefile(),
            }, result["id"]
        except:
            return {}, ""

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        ytdl_opts = {"quiet": True, "cookiefile": cookiefile()}
        with YoutubeDL(ytdl_opts) as ydl:
            r = ydl.extract_info(link, download=False)
            return [{
                "format": f.get("format"), "filesize": f.get("filesize"), 
                "format_id": f.get("format_id"), "ext": f.get("ext"), 
                "format_note": f.get("format_note"), "yturl": link
            } for f in r.get("formats", [])], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        a = VideosSearch(link, limit=10)
        res = await a.next()
        result = res.get("result", [])
        idx = query_type if query_type < len(result) else 0
        if not result: return "Unknown", "00:00", "", ""
        return result[idx]["title"], result[idx]["duration"], result[idx]["thumbnails"][0]["url"].split("?")[0], result[idx]["id"]

    async def download_thumb(self, url):
        return url 

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["title"] if res["result"] else "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["duration"] if res["result"] else "00:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        res = await results.next()
        return res["result"][0]["thumbnails"][0]["url"].split("?")[0] if res["result"] else ""

    async def search(self, query: str, limit: int = 10):
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

    async def invalidate_direct_cache(self, vid_or_link): pass
    async def clear_direct_cache(self): pass

YouTube = YouTubeAPI()

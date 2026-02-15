# plugins/ai/handlers.py
# Authored By Certified Coders (c) 2026
# AI Handler System - Pure Text Edition
# Features: Streaming, Session Management, Admin Control.

import os
import re
import logging
import asyncio
from typing import Dict, Optional, Union, Set

# Pyrogram
from pyrogram import filters, Client
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatAction
)

# Project Imports
from AnnieXMedia import app
from config import OWNER_ID

# Engine Imports (Text Only)
from .engine import (
    ask_ollama_stream,
    clear_user_memory,
    get_engine_status,
    set_engine_state
)

# ------------------------------------------------------------------
# CONFIGURATION & LOGGING
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_AI_Handlers")
logger.setLevel(logging.INFO)

# Setup Sudo/Owner Filters
if isinstance(OWNER_ID, (list, tuple, set)):
    SUDO_USERS = set(OWNER_ID)
else:
    SUDO_USERS = {OWNER_ID}

SUDO_FILTER = filters.user(list(SUDO_USERS))

# ------------------------------------------------------------------
# SESSION MANAGEMENT CLASS
# ------------------------------------------------------------------
class SessionManager:
    """
    Manages active chat sessions for 'Permanent AI' mode.
    Handles timeouts and chat isolation.
    """
    def __init__(self):
        # Structure: {user_id: {"chat_id": int, "task": asyncio.Task}}
        self._sessions: Dict[int, Dict[str, Union[int, asyncio.Task]]] = {}
        self._lock = asyncio.Lock()

    async def start_session(self, client: Client, user_id: int, chat_id: int):
        """Starts or refreshes a user session."""
        async with self._lock:
            # Cancel existing timer if present
            if user_id in self._sessions:
                old_task = self._sessions[user_id].get("task")
                if old_task and not old_task.done():
                    old_task.cancel()

            # Start new inactivity monitor
            task = asyncio.create_task(self._inactivity_monitor(client, user_id, chat_id))
            self._sessions[user_id] = {
                "chat_id": chat_id,
                "task": task
            }

    async def end_session(self, user_id: int):
        """Manually ends a session."""
        async with self._lock:
            if user_id in self._sessions:
                task = self._sessions[user_id].get("task")
                if task and not task.done():
                    task.cancel()
                del self._sessions[user_id]

    def is_active(self, user_id: int, chat_id: int) -> bool:
        """Checks if user has an active session in specific chat."""
        if user_id not in self._sessions:
            return False
        return self._sessions[user_id]["chat_id"] == chat_id

    async def _inactivity_monitor(self, client: Client, user_id: int, chat_id: int):
        """Background task: Ends session after 60s of silence."""
        try:
            await asyncio.sleep(60)
            
            async with self._lock:
                if user_id in self._sessions:
                    del self._sessions[user_id]
            
            try:
                await client.send_message(chat_id, "تم انهاء وضع الذكاء الدائم لعدم وجود رد.")
            except Exception as e:
                logger.warning(f"Failed to send timeout message: {e}")

        except asyncio.CancelledError:
            pass

# Initialize Manager
SESSIONS = SessionManager()

# ------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------
def extract_prompt_text(text: str) -> str:
    """Removes trigger words from the prompt."""
    triggers = ["ذكاء", "يا بوت", "بوت", "بقولك"]
    pattern = r"^(" + "|".join(triggers) + r")(\s+|$)"
    match = re.match(pattern, text or "", re.IGNORECASE)
    
    if match:
        return text[match.end():].strip()
    return (text or "").strip()

def is_trigger_message(text: str) -> bool:
    """Checks if message starts with a trigger word."""
    triggers = ["ذكاء", "يا بوت", "بوت", "بقولك"]
    pattern = r"^(" + "|".join(triggers) + r")"
    return bool(re.match(pattern, text or "", re.IGNORECASE))

# ------------------------------------------------------------------
# COMMAND: PERMANENT AI (ذكاء دائم)
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(ذكاء دائم)$") & ~filters.bot)
async def enable_permanent_ai(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    await SESSIONS.start_session(client, user_id, chat_id)
    await message.reply_text(
        "تم تفعيل وضع الذكاء الدائم.\n"
        "سيتم الرد عليك في هذا الجروب فقط.\n"
        "سيتم الاغلاق تلقائيا بعد دقيقة من الصمت."
    )

@app.on_message(filters.regex(r"^(كفاية|خروج)$") & ~filters.bot)
async def disable_permanent_ai(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id in SESSIONS._sessions:
        await SESSIONS.end_session(user_id)
        await message.reply_text("تم ايقاف الذكاء الدائم.")
    else:
        await message.reply_text("الوضع غير مفعل اصلا.")

# ------------------------------------------------------------------
# COMMAND: CLEAR MEMORY (مسح ذاكرتي)
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(مسح ذاكرتي)$") & ~filters.bot)
async def clear_memory_handler(client: Client, message: Message):
    clear_user_memory(message.from_user.id)
    await message.reply_text("تم مسح سجل المحادثة الخاص بك.")

# ------------------------------------------------------------------
# ADMIN CONTROL PANEL
# ------------------------------------------------------------------
@app.on_message(filters.regex(r"^(اوامر الذكاء|كيب ذكاء)$") & SUDO_FILTER)
async def admin_panel(client: Client, message: Message):
    status = get_engine_status()
    state_text = "مفعل" if status["enabled"] else "معطل"
    
    text = (
        "**لوحة تحكم الذكاء الاصطناعي**\n\n"
        f"• الحالة: {state_text}\n"
        f"• المحرك: {status['model']}\n"
        f"• المستخدمين النشطين: {status['active_users']}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("اوامر المستخدمين", callback_data="ai_help")],
        [InlineKeyboardButton("تشغيل / ايقاف", callback_data="ai_toggle")],
        [InlineKeyboardButton("تنظيف الذاكرة", callback_data="ai_flush")],
        [InlineKeyboardButton("اعادة تشغيل", callback_data="ai_reboot")],
        [InlineKeyboardButton("اغلاق", callback_data="ai_close")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("^ai_"))
async def admin_callbacks(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id

    if user_id not in SUDO_USERS and data != "ai_help":
        await query.answer("هذا الامر للمطورين فقط.", show_alert=True)
        return

    if data == "ai_help":
        help_text = (
            "اوامر المستخدم:\n"
            "- ذكاء <سؤال>\n"
            "- ذكاء دائم\n"
            "- كفاية (لانهاء الوضع الدائم)\n"
            "- مسح ذاكرتي"
        )
        await query.answer(help_text, show_alert=True)

    elif data == "ai_toggle":
        status = get_engine_status()
        new_state = not status["enabled"]
        set_engine_state(new_state)
        await query.answer("تم تغيير الحالة.", show_alert=True)
        new_status_text = "مفعل" if new_state else "معطل"
        try:
            await query.message.edit_text(
                f"**لوحة تحكم الذكاء الاصطناعي**\n\n• الحالة: {new_status_text}\n• المحرك: {status['model']}",
                reply_markup=query.message.reply_markup
            )
        except:
            pass

    elif data == "ai_flush":
        SESSIONS._sessions.clear()
        await query.answer("تم تصفير الجلسات.", show_alert=True)

    elif data == "ai_reboot":
        await query.answer("جاري اعادة التشغيل...", show_alert=True)
        os._exit(0)

    elif data == "ai_close":
        await query.message.delete()

# ------------------------------------------------------------------
# MAIN AI MESSAGE HANDLER
# ------------------------------------------------------------------
@app.on_message(filters.text & ~filters.bot, group=60)
async def main_ai_handler(client: Client, message: Message):
    """
    Main handler for text processing.
    """
    engine_status = get_engine_status()
    # If engine disabled, ignore everyone except sudo
    if not engine_status["enabled"] and message.from_user.id not in SUDO_USERS:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    
    should_reply = False
    
    # Check 1: Is user in Permanent AI mode?
    if SESSIONS.is_active(user_id, chat_id):
        should_reply = True
        await SESSIONS.start_session(client, user_id, chat_id) # Refresh timer
    
    # Check 2: Did user use a trigger word?
    elif is_trigger_message(message.text):
        should_reply = True
        
    if not should_reply:
        return

    # Extract clean prompt
    prompt = extract_prompt_text(message.text)
    
    # Handle empty prompts in permanent mode
    if not prompt:
        if SESSIONS.is_active(user_id, chat_id):
            prompt = "مرحبا" # Default greeting
        else:
            return

    # Send placeholder
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    wait_msg = await message.reply_text("...")

    # Callback to update message in real-time
    async def update_response_text(text: str):
        try:
            if text and text != wait_msg.text:
                # Telegram limit is 4096, safety buffer
                safe_text = text[:4000]
                await wait_msg.edit(safe_text)
        except Exception:
            pass

    # Call Engine
    try:
        final_reply = await ask_ollama_stream(
            user_id=user_id,
            prompt=prompt,
            on_update=update_response_text
        )

        # Final update
        if final_reply and final_reply != wait_msg.text:
            await wait_msg.edit(final_reply[:4000])
            
    except Exception as e:
        logger.error(f"Handler Error: {e}")
        await wait_msg.edit("حدث خطأ اثناء المعالجة.")

# plugins/ai/engine.py
# Authored By Certified Coders (c) 2026
# DeepSeek-R1 Local Inference Engine - H200 Optimized
# Strict No-Emoji Policy Enforced

import logging
import json
import time
import asyncio
import aiohttp
from typing import Dict, List, Optional, Callable, Any

# ------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------

OLLAMA_API_URL = "http://localhost:11434/api/chat"
CURRENT_MODEL = "deepseek-r1:70b"

MAX_HISTORY_LENGTH = 15
MAX_CONTEXT_TOKENS = 8192
REQUEST_TIMEOUT = 120

GENERATION_OPTIONS = {
    "temperature": 0.6,
    "top_p": 0.9,
    "num_ctx": MAX_CONTEXT_TOKENS,
    "num_predict": 2048,
    "repeat_penalty": 1.1
}

# ------------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------------
logger = logging.getLogger("AnnieX_DeepSeek_Engine")
logger.setLevel(logging.INFO)

# ------------------------------------------------------------------
# MEMORY MANAGEMENT CLASS
# ------------------------------------------------------------------
class MemoryManager:
    def __init__(self):
        self._history: Dict[int, List[Dict[str, str]]] = {}
        self._last_access: Dict[int, float] = {}
        self._max_users = 200

    def get_history(self, user_id: int) -> List[Dict[str, str]]:
        self._last_access[user_id] = time.time()
        return self._history.get(user_id, [])

    def add_message(self, user_id: int, role: str, content: str):
        if user_id not in self._history:
            self._history[user_id] = []
        
        self._history[user_id].append({"role": role, "content": content})
        self._last_access[user_id] = time.time()

        if len(self._history[user_id]) > MAX_HISTORY_LENGTH:
            # Keep system prompt if exists, and trim older messages
            # Simply slicing for now to keep it robust
            self._history[user_id] = self._history[user_id][-MAX_HISTORY_LENGTH:]

    def clear_history(self, user_id: int):
        if user_id in self._history:
            del self._history[user_id]
        if user_id in self._last_access:
            del self._last_access[user_id]

    def cleanup_old_sessions(self):
        if len(self._history) < self._max_users:
            return

        current_time = time.time()
        users_to_delete = [
            uid for uid, timestamp in self._last_access.items()
            if current_time - timestamp > 3600
        ]
        
        for uid in users_to_delete:
            self.clear_history(uid)
            
        if users_to_delete:
            logger.info(f"Memory Cleanup: Removed {len(users_to_delete)} idle sessions.")

MEMORY = MemoryManager()

# ------------------------------------------------------------------
# ENGINE STATE
# ------------------------------------------------------------------
class EngineState:
    def __init__(self):
        self.enabled: bool = True
        self.system_prompt: str = (
            "انت مساعد ذكي ومتطور. "
            "اجاباتك دقيقة ومختصرة ومفيدة. "
            "تحدث باللغة العربية بطلاقة. "
            "لا تستخدم الايموجي ابدا في ردودك. "
            "كن مهذبا ومحترفا."
        )

# Exported Instance (Fixed Name to match __init__)
ENGINE = EngineState()

# ------------------------------------------------------------------
# CORE INFERENCE FUNCTION
# ------------------------------------------------------------------
async def ask_ollama_stream(
    user_id: int,
    prompt: str,
    system_prompt: Optional[str] = None,
    on_update: Optional[Callable[[str], Any]] = None
) -> str:
    
    if not ENGINE.enabled:
        return "النظام متوقف حاليا للصيانة."

    messages = []
    sys_prompt_text = system_prompt or ENGINE.system_prompt
    messages.append({"role": "system", "content": sys_prompt_text})
    
    history = MEMORY.get_history(user_id)
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": CURRENT_MODEL,
        "messages": messages,
        "stream": True,
        "options": GENERATION_OPTIONS
    }

    full_response = ""
    last_update_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_API_URL, json=payload) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API Error: {response.status} - {error_text}")
                    return f"حدث خطأ في الخادم الداخلي: {response.status}"

                async for line in response.content:
                    if not line:
                        continue
                    try:
                        # Decode bytes to string
                        line_text = line.decode('utf-8')
                        chunk_data = json.loads(line_text)
                        
                        if "message" in chunk_data:
                            content = chunk_data["message"].get("content", "")
                            if content:
                                full_response += content
                                current_time = time.time()
                                if on_update and (current_time - last_update_time > 0.8):
                                    try:
                                        if asyncio.iscoroutinefunction(on_update):
                                            await on_update(full_response)
                                        else:
                                            on_update(full_response)
                                        last_update_time = current_time
                                    except Exception:
                                        pass
                                        
                        if chunk_data.get("done", False):
                            break
                            
                    except json.JSONDecodeError:
                        continue

    except asyncio.TimeoutError:
        return "عذرا، استغرق الخادم وقتا طويلا للرد. حاول مرة اخرى."
    except Exception as e:
        logger.exception(f"Error in ask_ollama_stream: {e}")
        return "حدث خطأ غير متوقع اثناء المعالجة."

    if full_response.strip():
        MEMORY.add_message(user_id, "user", prompt)
        MEMORY.add_message(user_id, "assistant", full_response)
        
        if len(MEMORY._history) % 10 == 0:
            MEMORY.cleanup_old_sessions()

    return full_response

# ------------------------------------------------------------------
# PUBLIC EXPORTS & HELPERS
# ------------------------------------------------------------------

def clear_user_memory(user_id: int):
    MEMORY.clear_history(user_id)

def toggle_model(enable: Optional[bool] = None) -> bool:
    """تبديل حالة تفعيل الذكاء الاصطناعي"""
    if enable is not None:
        ENGINE.enabled = enable
    else:
        ENGINE.enabled = not ENGINE.enabled
    return ENGINE.enabled

def get_engine_status():
    return {
        "model": CURRENT_MODEL,
        "enabled": ENGINE.enabled,
        "active_users": len(MEMORY._history)
    }

__all__ = [
    "ENGINE", 
    "ask_ollama_stream", 
    "clear_user_memory", 
    "toggle_model", 
    "get_engine_status"
]

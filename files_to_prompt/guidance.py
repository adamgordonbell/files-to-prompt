import hashlib
import os
import threading
import types
from typing import Dict, List, Optional

import diskcache as dc
import openai
import platformdirs

Message = Dict[str, str]

# Create a thread-local object to store the current_role
_thread_locals: threading.local = threading.local()

def get_current_role() -> Optional[str]:
    """Return the current role for the current thread."""
    return getattr(_thread_locals, "current_role", None)

def set_current_role(role: Optional[str]) -> None:
    """Set the current role for the current thread."""
    _thread_locals.current_role = role

class Model:
    def __init__(self, model: str):
        self.model = model
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.messages: List[Message] = []
        self.response: Dict[str, str] = {}
        cache_path = os.path.join(platformdirs.user_cache_dir("guidance"), "openai.tokens")
        self.cache = dc.Cache(cache_path, size_limit=int(1e12), eviction_policy="none")

    def __iadd__(self, message: str) -> 'Model':
        current_role = get_current_role()
        if current_role:
            self.messages.append({"role": current_role, "content": message.strip()})
        return self

    def __add__(self, message: str) -> 'Model':
        self.__iadd__(message)
        return self

    def _hash_prompt(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.model}{prompt}".encode()).hexdigest()

    def gen(self, context: str, max_tokens: int = 300, temperature: float = 0.0) -> None:
        prompt = "\n".join([f"{message['role']}: {message['content']}" for message in self.messages])
        if temperature == 0:
            cache_key = self._hash_prompt(prompt)
            if cache_key in self.cache:
                # print("Cached")
                cached_response = self.cache[cache_key]
                self.messages.append({"role": "assistant", "content": cached_response})
                self.response[context] = cached_response
                return
        # print("Request...")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=temperature
        )
        assistant_message = response.choices[0].message.content or ""
        self.messages.append({"role": "assistant", "content": assistant_message})
        self.response[context] = assistant_message
        if temperature == 0:
            self.cache[cache_key] = assistant_message

    def clear(self) -> None:
        self.messages = []
        self.response = {}

    def __getitem__(self, key: str) -> str:
        return self.response[key]

    def __str__(self) -> str:
        formatted_messages = []
        for message in self.messages:
            role_tag = f"<{message['role']}>"
            end_tag = f"</{message['role']}>"
            formatted_messages.append(f"{role_tag}\n{message['content']}\n{end_tag}")
        return "\n".join(formatted_messages)

# Context managers for user and assistant roles
class user:
    def __enter__(self) -> None:
        set_current_role("user")

    def __exit__(self, _exc_type: Optional[BaseException], _exc_val: Optional[BaseException], _exc_tb: Optional[types.TracebackType]) -> None:
        set_current_role(None)

class assistant:
    def __enter__(self) -> None:
        set_current_role("assistant")

    def __exit__(self, _exc_type: Optional[BaseException], _exc_val: Optional[BaseException], _exc_tb: Optional[types.TracebackType]) -> None:
        set_current_role(None)

class system:
    def __enter__(self) -> None:
        set_current_role("system")

    def __exit__(self, _exc_type: Optional[BaseException], _exc_val: Optional[BaseException], _exc_tb: Optional[types.TracebackType]) -> None:
        set_current_role(None)

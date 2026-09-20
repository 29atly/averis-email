"""Explicit .env loading; process environment takes precedence."""
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    provider: Literal["nvidia", "gemini", "huggingface"]
    model: str = Field(min_length=1)
    api_key: SecretStr
    base_url: str
    timeout: float = Field(default=60, gt=0, le=300)
    max_input_chars: int = Field(default=50000, gt=0)
    max_output_tokens: int = Field(default=1024, gt=0)

    @classmethod
    def from_env(cls, provider: str | None = None, env_file: str | Path = ".env"):
        env = {**dotenv_values(env_file), **os.environ}
        provider = provider or env.get("EMAIL_LLM_PROVIDER", "gemini")
        choices = {
            "nvidia": ("NVIDIA", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
            "gemini": ("GEMINI", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta"),
            "huggingface": ("HF", "HF_TOKEN", "https://router.huggingface.co/v1"),
        }
        if provider not in choices:
            raise ValueError("Provider must be nvidia, gemini, or huggingface")
        prefix, key_name, base = choices[provider]
        key, model = env.get(key_name, ""), env.get(f"{prefix}_MODEL", "")
        if not key or not key.strip() or not model or not model.strip():
            raise ValueError(f"Set {key_name} and {prefix}_MODEL in the environment or .env")
        return cls(provider=provider, model=model.strip(), api_key=key.strip(),
                   base_url=env.get(f"{prefix}_BASE_URL") or base,
                   timeout=env.get("EMAIL_LLM_TIMEOUT", 60),
                   max_input_chars=env.get("EMAIL_LLM_MAX_INPUT_CHARS", 50000),
                   max_output_tokens=env.get("EMAIL_LLM_MAX_OUTPUT_TOKENS", 1024))

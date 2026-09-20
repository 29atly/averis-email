import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr


class LayaSettings(BaseModel):
    checkpoint: Literal["auto", "english", "multilingual"] = "auto"
    device: Literal["cpu", "mps", "cuda"] = "cpu"
    revision: str = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"
    cache_dir: Path = Path(".cache/laya")
    local_files_only: bool = False
    hf_token: SecretStr | None = None
    min_probability: float = Field(default=0.80, ge=0, le=1, allow_inf_nan=False)
    min_margin: float = Field(default=0.20, ge=0, le=1, allow_inf_nan=False)
    min_act_probability: float = Field(default=0.50, ge=0, le=1, allow_inf_nan=False)
    max_input_chars: int = Field(default=50000, gt=0)

    @classmethod
    def from_env(cls, env_file=".env"):
        env = {**dotenv_values(env_file), **os.environ}
        fields = {key: env["LAYA_" + key.upper()] for key in cls.model_fields
                  if key != "hf_token" and env.get("LAYA_" + key.upper()) not in (None, "")}
        return cls(**fields, hf_token=env.get("HF_TOKEN") or None)

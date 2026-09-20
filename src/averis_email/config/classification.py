"""Supported classification strategies and user selection."""
from enum import StrEnum
import os

from dotenv import dotenv_values


class ClassifierMode(StrEnum):
    RULE_BASED = "rule_based"
    LAYA = "laya"
    LLM = "llm"


CLASSIFIER_MODES = tuple(mode.value for mode in ClassifierMode)
DEFAULT_CLASSIFIER_MODE = ClassifierMode.RULE_BASED


def get_classifier_mode(env_file=".env") -> ClassifierMode:
    env = {**dotenv_values(env_file), **os.environ}
    value = env.get("EMAIL_CLASSIFIER_MODE", DEFAULT_CLASSIFIER_MODE.value)
    try:
        return ClassifierMode(value)
    except ValueError:
        raise ValueError(f"EMAIL_CLASSIFIER_MODE must be one of: {', '.join(CLASSIFIER_MODES)}") from None

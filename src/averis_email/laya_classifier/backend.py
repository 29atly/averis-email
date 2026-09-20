"""Pinned local SDK adapter with explicit context checks before inference."""
import os
from typing import Protocol

from .config import LayaSettings


class ReviewNeeded(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Backend(Protocol):
    def predict(self, text: str, questions: dict) -> dict: ...


def check_context(agent, text, question):
    """Use the installed SDK formatter to reject silent state/head truncation."""
    from laya.common import build_sequence, render_options

    q = agent._to_internal(question)
    tok = agent.tok
    maximum = agent.cfg.get("max_len", 512)
    head_maximum = agent.cfg.get("head_max_len", 192)
    empty, markers = build_sequence(tok, "", q, maximum, head_maximum)
    full_head, _ = build_sequence(tok, "", q, 100000, 100000)
    options = render_options(q)
    if empty != full_head or len(markers) != len(options) or any(
        len(tok(" " + option.replace(tok.mask_token, " "), add_special_tokens=False)["input_ids"]) > 48
        for option in options
    ):
        raise ReviewNeeded("question_too_long", "Question/options exceed the checkpoint's prompt budget.")
    state_tokens = len(tok(text.replace(tok.mask_token, " "), add_special_tokens=False)["input_ids"])
    if state_tokens + len(empty) > maximum:
        raise ReviewNeeded("input_too_long", "Email exceeds the checkpoint's token budget; context was not truncated.")


class LocalLayaBackend:
    def __init__(self, settings: LayaSettings):
        self.settings = settings
        self._router = None

    def predict(self, text: str, questions: dict) -> dict:
        os.environ.setdefault("USE_TF", "0")
        try:
            import laya
            from huggingface_hub import snapshot_download
        except ImportError:
            raise ReviewNeeded("model_unavailable", "Install the local model dependencies with pip install -e '.[laya]'.") from None
        s = self.settings
        if self._router is None:
            self._router = laya.Router(device=s.device, max_loaded=2, auto_task_detection=False)
        # Detect language even when English is requested, to avoid known confident
        # misclassification on unsupported languages.
        detected = self._router.route(text, questions)
        if s.checkpoint == "english" and detected["model"] != "english":
            raise ReviewNeeded("unsupported_language", "English checkpoint requested for text detected as non-English.")
        decision = detected if s.checkpoint == "auto" else self._router.route(text, questions, model=s.checkpoint)
        name = decision["model"]
        if name not in self._router.loaded:
            prefix = "multilingual/" if name == "multilingual" else ""
            # SDK root loading otherwise downloads all bundled checkpoints.
            files = [prefix + file for file in (
                "model.safetensors", "rl_agent_config.json", "encoder/config.json",
                "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json")]
            directory = snapshot_download(
                "convaiinnovations/laya", revision=s.revision,
                allow_patterns=files, cache_dir=str(s.cache_dir),
                local_files_only=s.local_files_only,
                token=s.hf_token.get_secret_value() if s.hf_token else None)
            agent = laya.load(directory, device=s.device, subfolder="multilingual" if prefix else None)
            self._router.attach(name, agent)
        agent = self._router.load(name)
        for question in questions.values():
            check_context(agent, text, question)
        response = agent.predict(text, questions)
        response["routing"] = {**dict(decision), "revision": s.revision}
        return response

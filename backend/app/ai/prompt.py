"""Prompt construction (agent-runtime.md §7): versioned trusted templates plus labelled data.

The system prompt is a trusted, versioned file (``prompts/<task>/<version>.md``). Everything
that varies per call goes into the **user** message as labelled data sections. Untrusted text
(pasted text, customer messages) only ever appears inside ``<untrusted_*>`` sections and is
neutralised first.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai.injection import neutralise_untrusted

PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_prompt(task: str, version: str) -> str:
    path = PROMPTS_DIR / task / f"{version}.md"
    return path.read_text(encoding="utf-8").strip()


def render_system(task: str, version: str, variables: dict[str, str] | None = None) -> str:
    """The trusted system prompt. ``<<name>>`` markers are replaced by static, trusted text
    (e.g. the command registry description); ``{{...}}`` is left alone because it is the
    fact-placeholder syntax the prompts talk about."""
    text = load_prompt(task, version)
    for name, value in (variables or {}).items():
        text = text.replace(f"<<{name}>>", value)
    return text


def json_section(tag: str, data: Any) -> str:
    """A section of the owner's own data (trusted but still data), as compact JSON."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"<{tag}>\n{body}\n</{tag}>"


def data_section(tag: str, text: str) -> str:
    """A section holding text that is data even though it is not third-party (the owner's own
    command). Delimiters inside it are neutralised the same way."""
    return f"<{tag}>\n{neutralise_untrusted(text)}\n</{tag}>"


def untrusted_section(tag: str, text: str) -> str:
    """A section of third-party text. ``tag`` must start with ``untrusted_``."""
    if not tag.startswith("untrusted_"):
        raise ValueError("untrusted sections must be named untrusted_*")
    return f"<{tag}>\n{neutralise_untrusted(text)}\n</{tag}>"

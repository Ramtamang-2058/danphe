"""
social_agent.py — LLM-powered social media automation.
Reads conversations, understands context, generates intelligent replies.
Routes through Danphe's model selection (NVIDIA/Gemini).
"""
from __future__ import annotations
from typing import Any
from collections.abc import Iterator
import json
from datetime import datetime
from pathlib import Path

from danphe import router
from danphe.llm import nvidia


# ── Conversation Context Storage ──────────────────────────────────────────────


class ConversationContext:
    """In-memory conversation history with LLM-aware formatting."""

    def __init__(self, user_id: str, platform: str, personality: str = ""):
        self.user_id = user_id
        self.platform = platform
        self.personality = personality
        self.messages: list[dict] = []
        self.metadata: dict[str, Any] = {}

    def add_message(self, sender: str, text: str, timestamp: str = ""):
        """Add a message to conversation history."""
        if not timestamp:
            timestamp = datetime.now().isoformat()
        self.messages.append({
            "sender": sender,
            "text": text,
            "timestamp": timestamp,
        })

    def get_summary(self, max_messages: int = 20) -> str:
        """Format conversation for LLM context (most recent first)."""
        recent = self.messages[-max_messages:]
        lines = [f"=== Conversation with {self.user_id} on {self.platform} ==="]
        for msg in recent:
            sender = "You" if msg["sender"] == "self" else msg["sender"]
            lines.append(f"[{msg['timestamp']}] {sender}: {msg['text']}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for storage/debugging."""
        return {
            "user_id": self.user_id,
            "platform": self.platform,
            "messages": self.messages,
            "metadata": self.metadata,
        }


# ── Reply Generation ──────────────────────────────────────────────────────────


class ReplyGenerator:
    """Generate context-aware replies using LLM."""

    # Sound like a real person, not an AI
    DEFAULT_PERSONALITY = (
        "You are Ram, a real person replying to a friend on Instagram. "
        "You are a young Nepali guy — casual, warm, genuine. "
        "You text exactly like a real human: short, natural, sometimes mixed Nepali-English.\n\n"
        "Hard rules:\n"
        "- NEVER reveal you are an AI, bot, or assistant — you are Ram\n"
        "- NEVER start a sentence with 'I'\n"
        "- Keep replies to 1-2 sentences maximum — this is texting, not an essay\n"
        "- If someone asks you to hang out, meet up, or go outside: give a natural excuse "
        "(busy with work, tired, maybe later, have something to finish, etc.)\n"
        "- If someone asks a question, answer it naturally like a friend would\n"
        "- Match the language: if they text in Nepali, reply in Nepali; if English, reply in English\n"
        "- Do NOT use filler phrases like 'Absolutely!', 'Sure thing!', 'Of course!'\n"
        "- Emoji only if the other person used them first\n"
        "- Sound real — a little tired, a little busy, but always friendly"
    )

    def build_system(self, platform: str, context: ConversationContext) -> str:
        """Build LLM system prompt with personality and conversation context."""
        if self.system_prompt:
            return self.system_prompt

        lines = [
            self.personality,
            "",
            f"Platform: {platform}",
            "",
            "Conversation so far (reply to the LAST message from the other person only):",
            context.get_summary(max_messages=15),
        ]
        return "\n".join(lines)

    # Class-level model preference — set via ReplyGenerator(model="nvidia"|"gemini"|"auto")
    SUPPORTED_MODELS = ("auto", "gemini", "nvidia")

    def __init__(self, personality: str = "", system_prompt: str = "", model: str = "auto"):
        if personality:
            # Append custom tone on top of the base identity rules
            self.personality = self.DEFAULT_PERSONALITY + f"\n\nTone override: {personality}"
        else:
            self.personality = self.DEFAULT_PERSONALITY
        self.system_prompt = system_prompt
        self.model = model if model in self.SUPPORTED_MODELS else "auto"

    def _call_gemini(self, messages: list[dict], system: str, stream: bool):
        """Try Gemini Flash. Raises on 429 as RuntimeError('RATE_LIMITED ...')."""
        from danphe.llm import gemini
        try:
            if stream:
                return gemini.stream(messages, system=system)
            return gemini.complete(messages, system=system)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                import re as _re
                delay = _re.search(r"retry in (\d+)", err)
                wait = f" (retry in {delay.group(1)}s)" if delay else ""
                raise RuntimeError(f"RATE_LIMITED{wait}") from e
            raise

    def _call_nvidia(self, messages: list[dict], system: str, stream: bool):
        """Try NVIDIA fast tier (glm-4.7). Always uses fast — social replies are short."""
        from danphe import config as _cfg
        if not _cfg.NVIDIA_API_KEY:
            raise RuntimeError("no NVIDIA key")
        if stream:
            return nvidia.stream(messages, model_tier="fast", system=system)
        return nvidia.complete(messages, model_tier="fast", system=system)

    def generate(
        self,
        context: ConversationContext,
        platform: str = "instagram",
        max_length: int = 500,
        stream: bool = False,
    ) -> str:
        """
        Generate a reply.
        model="auto"   → Gemini first, NVIDIA fast as fallback
        model="gemini" → Gemini only
        model="nvidia" → NVIDIA fast only
        """
        if not context.messages:
            return "haha k cha"

        last_msg = context.messages[-1]
        system = self.build_system(platform, context)
        messages = [
            {
                "role": "user",
                "content": (
                    f"Their last message: \"{last_msg['text']}\"\n\n"
                    f"Write a short natural reply (max {max_length} chars). "
                    f"Reply only — no explanation, no quotes, just the reply text."
                ),
            }
        ]

        if self.model == "nvidia":
            return self._call_nvidia(messages, system, stream)

        if self.model == "gemini":
            return self._call_gemini(messages, system, stream)

        # auto: Gemini first (faster), NVIDIA fast as fallback
        try:
            return self._call_gemini(messages, system, stream)
        except RuntimeError as e:
            if "RATE_LIMITED" in str(e):
                print(f"  [gemini] {e} — falling back to NVIDIA fast")
            else:
                raise
        except Exception as e:
            print(f"  [gemini] failed: {e} — falling back to NVIDIA fast")

        try:
            return self._call_nvidia(messages, system, stream)
        except Exception as e:
            raise RuntimeError(f"All models failed. Last error: {e}") from e

    def generate_stream(self, context: ConversationContext, platform: str = "instagram"):
        """Stream reply."""
        result = self.generate(context, platform=platform, stream=True)
        if hasattr(result, "__iter__") and not isinstance(result, str):
            yield from result
        else:
            yield result


# ── Analytics & Memory ────────────────────────────────────────────────────────


class SessionMemory:
    """Manage multiple conversations across platforms."""

    def __init__(self, cache_file: Path | None = None):
        self.conversations: dict[str, ConversationContext] = {}
        self.cache_file = cache_file or Path.home() / ".danphe" / "social_memory.json"

    def get_or_create(self, user_id: str, platform: str, personality: str = "") -> ConversationContext:
        """Get existing or create new conversation context."""
        key = f"{platform}:{user_id}"
        if key not in self.conversations:
            self.conversations[key] = ConversationContext(user_id, platform, personality)
        return self.conversations[key]

    def save(self):
        """Persist conversations to disk."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.to_dict() for k, v in self.conversations.items()}
        self.cache_file.write_text(json.dumps(data, indent=2))

    def load(self):
        """Restore conversations from disk."""
        if not self.cache_file.exists():
            return
        try:
            data = json.loads(self.cache_file.read_text())
            for key, conv_data in data.items():
                ctx = ConversationContext(
                    conv_data["user_id"],
                    conv_data["platform"],
                )
                ctx.messages = conv_data.get("messages", [])
                ctx.metadata = conv_data.get("metadata", {})
                self.conversations[key] = ctx
        except Exception as e:
            print(f"Failed to load social memory: {e}")

    def summarize_all(self) -> str:
        """Get summary of all active conversations."""
        lines = ["# Social Media Summary\n"]
        for key, ctx in self.conversations.items():
            msg_count = len(ctx.messages)
            lines.append(f"- {key}: {msg_count} messages")
        return "\n".join(lines)


# ── Conversation Fetcher (Platform-agnostic interface) ──────────────────────


class ConversationFetcher:
    """Extract messages from browser automation (to be implemented per platform)."""

    async def fetch_instagram_dm(self, page, username: str) -> list[dict]:
        """Extract message history from Instagram DM thread."""
        # This would be called from the Playwright automation
        # Returns format: [{"sender": "username", "text": "...", "timestamp": "..."}, ...]
        pass

    async def fetch_whatsapp_chat(self, page, contact_name: str) -> list[dict]:
        """Extract message history from WhatsApp conversation."""
        pass

    async def fetch_telegram_chat(self, page, username: str) -> list[dict]:
        """Extract message history from Telegram conversation."""
        pass


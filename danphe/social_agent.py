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

    # Default Instagram personality: warm, professional, senior-friendly, playful
    DEFAULT_PERSONALITY = (
        "a warm, witty, and slightly fruity personality — like a smart friend "
        "who happens to be professional. You write like someone who respects the "
        "person they're talking to (treat them as a wise senior), keeps things "
        "light and fun, sneaks in a cheeky joke or playful observation when "
        "appropriate, but never loses professionalism. Short sentences. No slang. "
        "A little humor goes a long way. Emoji are welcome but used sparingly."
    )

    def __init__(self, personality: str = "", system_prompt: str = ""):
        self.personality = personality or self.DEFAULT_PERSONALITY
        self.system_prompt = system_prompt

    def build_system(self, platform: str, context: ConversationContext) -> str:
        """Build LLM system prompt with personality and context."""
        if self.system_prompt:
            return self.system_prompt

        lines = [
            f"You are replying on behalf of the user on {platform}.",
            f"Personality: {self.personality}",
            f"",
            f"Rules:",
            f"- Read the full conversation below before replying.",
            f"- Reply ONLY to the last message from the other person.",
            f"- Keep it under 3 sentences unless the message demands more.",
            f"- Be warm and genuine — never robotic or copy-paste sounding.",
            f"- If the other person is a senior or elder, show extra respect while keeping wit.",
            f"",
            context.get_summary(max_messages=15),
        ]
        return "\n".join(lines)

    def generate(
        self,
        context: ConversationContext,
        platform: str = "instagram",
        max_length: int = 500,
        stream: bool = False,
    ) -> str | Iterator:
        """Generate a reply to the last message in context."""
        if not context.messages:
            return "Hi! How can I help?"

        last_msg = context.messages[-1]
        system = self.build_system(platform, context)

        messages = [
            {"role": "user", "content": f"Last message from {last_msg['sender']}: {last_msg['text']}\n\nGenerate a short, natural reply (max {max_length} chars):"}
        ]

        # Pick model via danphe router
        backend, tier = router.pick(messages)

        if backend == "nvidia":
            if stream:
                return nvidia.stream(messages, model_tier=tier, system=system)
            else:
                return nvidia.complete(messages, model_tier=tier, system=system)
        elif backend == "gemini":
            # Try to import gemini if available
            try:
                from danphe.llm import gemini
                if stream:
                    return gemini.stream(messages, system=system)
                else:
                    return gemini.complete(messages, system=system)
            except ImportError:
                # Fallback
                return f"Thanks for your message! I'd love to help with '{last_msg['text'][:50]}...'"
        else:
            # Fallback: simple template
            return f"Thanks for your message! I'd love to help with {last_msg['text'][:30]}..."

    def generate_stream(
        self,
        context: ConversationContext,
        platform: str = "instagram",
    ):
        """Stream reply generation token-by-token."""
        if not context.messages:
            yield "Hi! How can I help?"
            return

        system = self.build_system(platform, context)
        last_msg = context.messages[-1]

        messages = [
            {"role": "user", "content": f"Last message: {last_msg['text']}\n\nReply naturally:"}
        ]

        backend, tier = router.pick(messages)

        if backend == "nvidia":
            yield from nvidia.stream(messages, model_tier=tier, system=system)
        elif backend == "gemini":
            try:
                from danphe.llm import gemini
                yield from gemini.stream(messages, system=system)
            except ImportError:
                yield "Thanks for your message!"
        else:
            yield "Thanks for your message!"


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


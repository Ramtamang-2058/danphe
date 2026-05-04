"""
social_config.py — Configuration for social media automation.
Personality templates, reply rules, and platform-specific settings.
"""
from dataclasses import dataclass
from enum import Enum


class Personality(Enum):
    """Pre-defined reply personalities."""

    FRIENDLY = "warm, friendly, and encouraging"
    PROFESSIONAL = "professional, formal, and concise"
    CASUAL = "casual, humorous, and laid-back"
    HELPFUL = "helpful, informative, and solution-oriented"
    EMPATHETIC = "empathetic, understanding, and supportive"
    WITTY = "witty, clever, and fun-loving"
    MINIMALIST = "brief, to-the-point, and efficient"
    NEPALI_MIXED = "nepali-english mixed like 'k gardai' - casual, friendly, uses Nepali slang with English"


@dataclass
class SocialConfig:
    """Configuration for social media automation."""

    # Browser settings
    headless: bool = False  # Show browser or run headless
    persistent: bool = True  # Save login sessions
    timeout: int = 30  # seconds for page waits
    scroll_history: int = 5  # times to scroll for older messages

    # LLM settings
    max_reply_length: int = 200  # Max characters per reply
    model_tier: str = "long"  # "fast", "long", or "reasoning"
    temperature: float = 0.8  # Reply creativity (0-1)

    # Platform-specific
    instagram: dict = None
    whatsapp: dict = None
    telegram: dict = None

    # Memory
    memory_file: str = "~/.danphe/social_memory.json"
    auto_save: bool = True

    def __post_init__(self):
        self.instagram = self.instagram or {
            "headless": self.headless,
            "data_dir": "./browser_data_ig",
        }
        self.whatsapp = self.whatsapp or {
            "headless": self.headless,
            "data_dir": "./browser_data_wa",
        }
        self.telegram = self.telegram or {
            "headless": self.headless,
            "data_dir": "./browser_data_tg",
        }


# Global config instance
SOCIAL_CONFIG = SocialConfig()


def set_personality(name: str) -> str:
    """Get personality prompt from enum or string."""
    try:
        return Personality[name.upper()].value
    except KeyError:
        return name  # Return as-is if not in enum


def get_system_prompt(platform: str, personality: str = "") -> str:
    """Get LLM system prompt for platform."""
    if not personality:
        personality = Personality.FRIENDLY.value

    prompts = {
        "instagram": f"You are a {personality} social media user replying to direct messages on Instagram. Keep responses concise (under 200 chars), natural, and engaging. Match the tone of the conversation.",

        "whatsapp": f"You are a {personality} person chatting on WhatsApp. Be conversational, warm, and authentic. Keep messages brief and to the point. Use casual language and emojis sparingly.",

        "telegram": f"You are a {personality} Telegram user. Be friendly, clear, and helpful. Format messages for readability. Keep it conversational.",

        "discord": f"You are a {personality} Discord user. Be casual, use emojis as appropriate, and keep responses engaged. Match server culture.",

        "twitter": f"You are a {personality} Twitter user replying to messages. Be witty, concise (under 280 chars), and engaging. Use relevant hashtags if appropriate.",
    }

    return prompts.get(platform, f"You are a {personality} assistant replying to messages.")


def get_context_rules(platform: str) -> dict:
    """Platform-specific rules for context analysis."""
    return {
        "instagram": {
            "ignore_stories": True,
            "include_typings": True,
            "respect_active_now": True,
            "auto_read_receipts": True,
        },
        "whatsapp": {
            "detect_typing": True,
            "respect_muted": False,
            "include_reactions": True,
            "handle_group_mentions": True,
        },
        "telegram": {
            "include_edits": True,
            "respect_silent_mode": True,
            "handle_bots": False,
            "preserve_formatting": True,
        },
    }.get(platform, {})


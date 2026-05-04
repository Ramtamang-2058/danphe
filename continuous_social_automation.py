"""
continuous_social_automation.py — Full conversation automation.
Continuously monitors for new messages and replies automatically.
Supports Nepali-English mixed language and persistent conversations.
"""
from __future__ import annotations
import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import Page, BrowserContext

from danphe.social_agent import (
    ConversationContext,
    ReplyGenerator,
    SessionMemory,
)
from danphe.social_config import Personality


class ContinuousConversationBot:
    """Full automation bot that monitors conversations continuously."""

    def __init__(
        self,
        platform: str,
        target: str,
        personality: str = "nepali-english mixed like 'k gardai'",
        check_interval: int = 30,  # seconds between checks
        max_conversation_length: int = 50,  # max messages to keep
    ):
        self.platform = platform
        self.target = target
        self.check_interval = check_interval
        self.max_conversation_length = max_conversation_length

        # Initialize components
        self.memory = SessionMemory()
        self.memory.load()

        self.generator = ReplyGenerator(personality=personality)
        self.ctx = self.memory.get_or_create(target, platform, personality)

        # State tracking
        self.last_message_count = len(self.ctx.messages)
        self.is_running = False
        self.reply_count = 0

    async def start_continuous_monitoring(self, page: Page):
        """Start continuous conversation monitoring and replying."""
        self.is_running = True
        print(f"\n🤖 Starting continuous automation for {self.target} on {self.platform}")
        print(f"   Personality: {self.ctx.personality}")
        print(f"   Check interval: {self.check_interval}s")
        print(f"   Press Ctrl+C to stop\n")

        try:
            while self.is_running:
                try:
                    await self._check_and_reply(page)
                    await asyncio.sleep(self.check_interval)
                except Exception as e:
                    print(f"   [error] Check failed: {e}")
                    await asyncio.sleep(self.check_interval)

        except KeyboardInterrupt:
            print(f"\n🛑 Stopped continuous monitoring for {self.target}")
            self.memory.save()

    def stop(self):
        """Stop the continuous monitoring."""
        self.is_running = False
        self.memory.save()

    async def _check_and_reply(self, page: Page):
        """Check for new messages and reply if needed."""
        try:
            # Read current conversation
            if self.platform == "instagram":
                from instra_automate.social_media import InstagramDMClient
                client = InstagramDMClient()
                messages = await client.read_messages(page, self.target)
            elif self.platform == "whatsapp":
                from instra_automate.social_media import WhatsAppClient
                client = WhatsAppClient()
                messages = await client.read_messages(page, self.target)
            else:
                print(f"   [error] Unsupported platform: {self.platform}")
                return

            # Update conversation context
            new_messages = []
            for msg in messages:
                # Check if this is a new message
                if not any(
                    existing["text"] == msg["text"] and
                    existing["timestamp"] == msg["timestamp"]
                    for existing in self.ctx.messages
                ):
                    new_messages.append(msg)

            # Add new messages to context
            for msg in new_messages:
                self.ctx.add_message(msg["sender"], msg["text"], msg["timestamp"])

            # Check if there are new messages from others (not from us)
            new_from_others = [
                msg for msg in new_messages
                if msg["sender"] != "self"
            ]

            if new_from_others:
                print(f"\n📨 New message(s) from {self.target}:")
                for msg in new_from_others[-3:]:  # Show last 3
                    print(f"   {msg['sender']}: {msg['text']}")

                # Generate and send reply
                await self._generate_and_send_reply(page)

                # Trim conversation if too long
                if len(self.ctx.messages) > self.max_conversation_length:
                    self.ctx.messages = self.ctx.messages[-self.max_conversation_length:]

                # Save memory
                self.memory.save()

        except Exception as e:
            print(f"   [error] Failed to check/reply: {e}")

    async def _generate_and_send_reply(self, page: Page):
        """Generate intelligent reply and send it."""
        try:
            print(f"   🤔 Generating reply...")

            # Generate reply using LLM
            reply = self.generator.generate(
                self.ctx,
                platform=self.platform,
                max_length=150  # Shorter for continuous chat
            )

            if not reply or reply.strip() == "":
                reply = "Got it! 👍"  # Fallback

            print(f"   💬 Reply: {reply}")

            # Send the reply
            if self.platform == "instagram":
                from instra_automate.social_media import InstagramDMClient
                client = InstagramDMClient()
                await client.send_message(page, self.target, reply)
            elif self.platform == "whatsapp":
                from instra_automate.social_media import WhatsAppClient
                client = WhatsAppClient()
                await client.send_message(page, self.target, reply)

            # Add our reply to context
            self.ctx.add_message("self", reply)
            self.reply_count += 1

            print(f"   ✅ Sent reply #{self.reply_count}")

        except Exception as e:
            print(f"   [error] Failed to generate/send reply: {e}")


# ── CLI Interface for Continuous Automation ───────────────────────────────


async def main():
    """CLI for continuous social media automation."""
    if len(sys.argv) < 4:
        print("Usage:")
        print("  python continuous_social_automation.py instagram @username [--interval SECS] [--personality 'style']")
        print("  python continuous_social_automation.py whatsapp 'Contact Name' [--interval SECS] [--personality 'style']")
        print("")
        print("Examples:")
        print("  python continuous_social_automation.py instagram @friend")
        print("  python continuous_social_automation.py whatsapp 'Ram' --interval 60")
        print("  python continuous_social_automation.py instagram @sister --personality 'nepali-english mixed like k gardai'")
        print("")
        print("Personalities:")
        print("  - 'nepali-english mixed like k gardai' (default)")
        print("  - 'friendly and encouraging'")
        print("  - 'casual and humorous'")
        print("  - 'professional and formal'")
        print("")
        print("The bot will continuously monitor for new messages and reply automatically.")
        print("Press Ctrl+C to stop.")
        sys.exit(1)

    platform = sys.argv[1].lower()
    target = sys.argv[2]

    # Parse arguments
    interval = 30  # default 30 seconds
    personality = "nepali-english mixed like 'k gardai'"

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--interval" and i + 1 < len(sys.argv):
            interval = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--personality" and i + 1 < len(sys.argv):
            personality = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    print(f"🚀 Starting continuous conversation automation")
    print(f"   Platform: {platform}")
    print(f"   Target: {target}")
    print(f"   Personality: {personality}")
    print(f"   Check interval: {interval}s")
    print("")

    try:
        # Initialize browser
        if platform == "instagram":
            from instra_automate.social_media import InstagramDMClient
            client = InstagramDMClient(headless=False)
            ctx = await client.launch()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await client.ensure_logged_in(page)
        elif platform == "whatsapp":
            from instra_automate.social_media import WhatsAppClient
            client = WhatsAppClient(headless=False)
            ctx = await client.launch()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            if not await client.ensure_logged_in(page):
                print("[error] Failed to log in to WhatsApp")
                await client.close()
                return
        else:
            print(f"[error] Unsupported platform: {platform}")
            return

        # Start continuous bot
        bot = ContinuousConversationBot(
            platform=platform,
            target=target,
            personality=personality,
            check_interval=interval
        )

        await bot.start_continuous_monitoring(page)

        # Cleanup
        if platform == "instagram":
            await client.close()
        else:
            await client.close()

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    except Exception as e:
        print(f"[error] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())


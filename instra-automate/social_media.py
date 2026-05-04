"""
social_media.py — Context-aware social media automation.
Reads conversations, generates intelligent replies via LLM.
Supports Instagram, WhatsApp, Telegram.
No timeouts — async/await with graceful handling.
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime

from playwright.async_api import async_playwright, Page, BrowserContext

from danphe.social_agent import (
    ConversationContext,
    ReplyGenerator,
    SessionMemory,
)


# ── Platform: Instagram ───────────────────────────────────────────────────────


class InstagramDMClient:
    """Instagram DM automation with conversation reading."""

    def __init__(self, headless: bool = False, persistent_dir: str = "./browser_data"):
        self.headless = headless
        self.persistent_dir = persistent_dir
        self.context: BrowserContext | None = None

    async def launch(self):
        """Start browser session."""
        p = await async_playwright().start()
        self.browser_p = p
        self.context = await p.firefox.launch_persistent_context(
            user_data_dir=self.persistent_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},  # type: ignore
        )
        return self.context

    async def close(self):
        """Clean up."""
        if self.context:
            await self.context.close()
        await self.browser_p.stop()

    async def ensure_logged_in(self, page: Page) -> bool:
        """Verify Instagram login or prompt user."""
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Check if logged in by looking for home feed icon
        already_logged_in = (
            await page.query_selector('a[href="/"]') and
            not await page.query_selector('input[name="username"]')
        )

        if not already_logged_in:
            print("\n>>> Browser is open. Please log in to Instagram in the browser window.")
            print(">>> Press ENTER here when you are logged in...")
            input()
            await page.wait_for_timeout(2000)

        return True

    async def read_messages(self, page: Page, username: str) -> list[dict]:
        """
        Extract all visible messages from Instagram DM thread.
        Returns: [{"sender": str, "text": str, "timestamp": str}, ...]
        """
        messages = []

        # Navigate to DM with user
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(2000)

        # Scroll up to see earlier messages
        msg_container = await page.query_selector('div[role="presentation"]')
        if msg_container:
            # Scroll up to load more history
            for _ in range(5):  # Scroll up 5 times to get more history
                await msg_container.evaluate(
                    "el => el.scrollTop = el.scrollTop - 300"
                )
                await page.wait_for_timeout(500)

        # Extract all message elements
        msg_elements = await page.query_selector_all('div[data-testid="message"]')
        if not msg_elements:
            # Fallback selector
            msg_elements = await page.query_selector_all('span[role="img"]')

        for elem in msg_elements:
            try:
                text = await elem.text_content()
                time_elem = await elem.query_selector('div[title]')
                timestamp = await time_elem.get_attribute('title') if time_elem else datetime.now().isoformat()

                # Try to determine if it's from me or them
                # This is heuristic: messages from us are typically on the right
                classes = await elem.get_attribute('class')
                is_from_me = 'outgoing' in classes if classes else False

                sender = "self" if is_from_me else username

                if text and text.strip():
                    messages.append({
                        "sender": sender,
                        "text": text.strip(),
                        "timestamp": timestamp,
                    })
            except Exception as e:
                print(f"  [warn] Failed to parse message: {e}")

        return messages

    async def navigate_to_dm(self, page: Page, username: str):
        """Navigate to specific DM thread."""
        # Go to DM inbox
        await page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Click compose/new message button if needed
        search_loc = page.locator('input[placeholder*="Search"]')
        if not await search_loc.count():
            for sel in ['div[role="button"][aria-label*="New"]', 'a[aria-label*="New message"]']:
                compose = page.locator(sel)
                if await compose.count():
                    await compose.first.click()
                    await page.wait_for_timeout(2000)
                    break

        # Wait for search box and type username
        await page.wait_for_selector('input[placeholder*="Search"]', timeout=10000)
        search_box = page.locator('input[placeholder*="Search"]').first
        await search_box.click()
        await search_box.fill(username)
        await page.wait_for_timeout(2500)

        # Click first matching result
        result = page.locator(f'span:has-text("{username}")').first
        if await result.count():
            await result.click()
            await page.wait_for_timeout(2000)
        else:
            raise ValueError(f"Could not find user '{username}' in Instagram DMs")

        # Click Next/Chat button if present
        for label in ["Next", "Chat"]:
            btn = page.locator(f'div[role="button"]:has-text("{label}")')
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(2000)
                break

    async def send_message(self, page: Page, username: str, message: str):
        """Send a message to user."""
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(2000)

        # Find message input
        box = None
        for sel in ['div[aria-label="Message"]', 'div[role="textbox"]', 'p[contenteditable="true"]']:
            loc = page.locator(sel)
            if await loc.count():
                box = loc.first
                print(f"  [info] Found message box: {sel}")
                break

        if box:
            await box.click()
            await page.wait_for_timeout(500)
            await box.type(message, delay=30)
            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            print(f"✓ Sent to {username}: {message}")
        else:
            raise RuntimeError("Could not find message input box")

    async def auto_reply(
        self,
        page: Page,
        username: str,
        generator: ReplyGenerator,
        personality: str = "",
    ):
        """
        Read messages from user, generate context-aware reply via LLM, send it.
        """
        print(f"\n[instagram] Reading conversation with {username}...")
        try:
            messages = await self.read_messages(page, username)
            print(f"  Loaded {len(messages)} messages")
        except Exception as e:
            print(f"  [error] Failed to read messages: {e}")
            return

        if not messages:
            print("  No messages found")
            return

        # Build conversation context
        ctx = ConversationContext(username, "instagram", personality)
        for msg in messages:
            ctx.add_message(msg["sender"], msg["text"], msg["timestamp"])

        # Display last few messages
        print(f"\n  Last 3 messages:")
        for msg in messages[-3:]:
            print(f"    {msg['sender']}: {msg['text']}")

        # Generate reply
        print(f"\n  Generating reply via LLM...")
        try:
            reply = generator.generate(ctx, platform="instagram", max_length=200)
            print(f"  Generated: {reply}\n")

            # Send it
            print(f"  Sending reply...")
            await self.send_message(page, username, reply)

        except Exception as e:
            print(f"  [error] Failed to generate/send reply: {e}")


# ── Platform: WhatsApp ────────────────────────────────────────────────────────


class WhatsAppClient:
    """WhatsApp Web automation with conversation reading."""

    def __init__(self, headless: bool = False, persistent_dir: str = "./browser_data_whatsapp"):
        self.headless = headless
        self.persistent_dir = persistent_dir
        self.context: BrowserContext | None = None

    async def launch(self):
        """Start browser session."""
        p = await async_playwright().start()
        self.browser_p = p
        self.context = await p.firefox.launch_persistent_context(
            user_data_dir=self.persistent_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},  # type: ignore
        )
        return self.context

    async def close(self):
        """Clean up."""
        if self.context:
            await self.context.close()
        await self.browser_p.stop()

    async def ensure_logged_in(self, page: Page) -> bool:
        """Verify WhatsApp login or show QR code."""
        await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
        print("\n>>> Waiting for WhatsApp to load (scan QR if first time)...")
        try:
            await page.wait_for_selector('div[role="textbox"]', timeout=60000)
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            print(f"  [error] WhatsApp login failed: {e}")
            return False

    async def read_messages(self, page: Page, contact_name: str) -> list[dict]:
        """Extract message history from WhatsApp conversation."""
        messages = []

        # Find and open contact
        search_selector = 'div[contenteditable="true"][title*="Search"]'
        search_box = await page.query_selector(search_selector)
        if search_box:
            await search_box.click()
            await search_box.type(contact_name, delay=50)
            await page.wait_for_timeout(2000)

            # Click contact
            contact = await page.query_selector(f'span[title="{contact_name}"]')
            if contact:
                await contact.click()
                await page.wait_for_timeout(2000)

        # Scroll up to load older messages
        msg_container = await page.query_selector('div[data-testid="conversation-panel-messages"]')
        if msg_container:
            for _ in range(5):
                await msg_container.evaluate("el => el.scrollTop = 0")
                await page.wait_for_timeout(500)

        # Extract messages
        msg_elements = await page.query_selector_all('div[data-testid="msg-container"]')
        for elem in msg_elements:
            try:
                text = await elem.text_content()
                timestamp_elem = await elem.query_selector('span[data-testid="message-text"]')
                timestamp = datetime.now().isoformat()

                # Check if outgoing (from me)
                classes = await elem.get_attribute('class')
                is_from_me = 'outgoing' in classes if classes else False

                sender = "self" if is_from_me else contact_name

                if text and text.strip():
                    messages.append({
                        "sender": sender,
                        "text": text.strip(),
                        "timestamp": timestamp,
                    })
            except Exception as e:
                pass  # Skip parsing errors

        return messages

    async def send_message(self, page: Page, contact_name: str, message: str):
        """Send WhatsApp message."""
        # Find and click contact
        search_box = await page.query_selector('div[contenteditable="true"][title*="Search"]')
        if search_box:
            await search_box.click()
            await search_box.type(contact_name, delay=50)
            await page.wait_for_timeout(2000)

            contact = await page.query_selector(f'span[title="{contact_name}"]')
            if contact:
                await contact.click()
                await page.wait_for_timeout(1000)

        # Type message
        msg_box = await page.query_selector('div[contenteditable="true"][title="Type a message"]')
        if msg_box:
            await msg_box.click()
            await msg_box.type(message, delay=30)
            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            print(f"✓ Sent to {contact_name}: {message}")
        else:
            raise RuntimeError("Could not find WhatsApp message box")

    async def auto_reply(
        self,
        page: Page,
        contact_name: str,
        generator: ReplyGenerator,
        personality: str = "",
    ):
        """Auto-reply on WhatsApp."""
        print(f"\n[whatsapp] Reading conversation with {contact_name}...")
        try:
            messages = await self.read_messages(page, contact_name)
            print(f"  Loaded {len(messages)} messages")
        except Exception as e:
            print(f"  [error] Failed to read messages: {e}")
            return

        if not messages:
            print("  No messages found")
            return

        ctx = ConversationContext(contact_name, "whatsapp", personality)
        for msg in messages:
            ctx.add_message(msg["sender"], msg["text"], msg["timestamp"])

        print(f"\n  Last 3 messages:")
        for msg in messages[-3:]:
            print(f"    {msg['sender']}: {msg['text']}")

        print(f"\n  Generating reply via LLM...")
        try:
            reply = generator.generate(ctx, platform="whatsapp", max_length=200)
            print(f"  Generated: {reply}\n")
            await self.send_message(page, contact_name, reply)
        except Exception as e:
            print(f"  [error] Failed to generate/send reply: {e}")


# ── CLI Interface ────────────────────────────────────────────────────────────


async def main():
    """CLI for social media automation."""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python social_media.py instagram <username> [--auto-reply] [--personality '<style>']")
        print("  python social_media.py whatsapp  <contact>  [--auto-reply] [--personality '<style>']")
        print("")
        print("Examples:")
        print('  python social_media.py instagram its_ramtamang --auto-reply')
        print('  python social_media.py whatsapp "Ram" --auto-reply --personality "casual and humorous"')
        sys.exit(1)

    platform = sys.argv[1].lower()
    target = sys.argv[2]
    auto_reply = "--auto-reply" in sys.argv
    personality = ""

    # Extract personality if provided
    if "--personality" in sys.argv:
        idx = sys.argv.index("--personality")
        if idx + 1 < len(sys.argv):
            personality = sys.argv[idx + 1]

    generator = ReplyGenerator(personality=personality)
    memory = SessionMemory()
    memory.load()

    try:
        if platform == "instagram":
            client = InstagramDMClient(headless=False)
            ctx = await client.launch()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            await client.ensure_logged_in(page)

            if auto_reply:
                await client.auto_reply(page, target, generator, personality)
            else:
                # Just read and display
                messages = await client.read_messages(page, target)
                ctx_obj = ConversationContext(target, "instagram", personality)
                for msg in messages:
                    ctx_obj.add_message(msg["sender"], msg["text"], msg["timestamp"])
                print(ctx_obj.get_summary())

            await client.close()

        elif platform == "whatsapp":
            client = WhatsAppClient(headless=False)
            ctx = await client.launch()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            if not await client.ensure_logged_in(page):
                print("[error] Failed to log in to WhatsApp")
                await client.close()
                return

            if auto_reply:
                await client.auto_reply(page, target, generator, personality)
            else:
                messages = await client.read_messages(page, target)
                ctx_obj = ConversationContext(target, "whatsapp", personality)
                for msg in messages:
                    ctx_obj.add_message(msg["sender"], msg["text"], msg["timestamp"])
                print(ctx_obj.get_summary())

            await client.close()

        else:
            print(f"[error] Unknown platform: {platform}")
            print("  Supported: instagram, whatsapp")

    except Exception as e:
        print(f"[error] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())


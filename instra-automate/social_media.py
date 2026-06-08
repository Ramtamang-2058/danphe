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
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

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

    async def _dismiss_popups(self, page: Page) -> None:
        """Dismiss Instagram notification prompts, save-login dialogs, and cookie banners."""
        popup_texts = [
            "Not Now", "Not now", "Maybe Later", "Decline optional cookies",
        ]
        for text in popup_texts:
            for role_sel in [f'button:has-text("{text}")', f'div[role="button"]:has-text("{text}")']:
                try:
                    loc = page.locator(role_sel).first
                    if await loc.is_visible(timeout=1200):
                        await loc.click()
                        await page.wait_for_timeout(400)
                except Exception:
                    pass

    async def ensure_logged_in(self, page: Page) -> bool:
        """Verify Instagram login or prompt user."""
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        already_logged_in = (
            await page.query_selector('a[href="/"]') and
            not await page.query_selector('input[name="username"]')
        )

        if not already_logged_in:
            print("\n>>> Browser is open. Please log in to Instagram in the browser window.")
            print(">>> Press ENTER here when you are logged in...")
            input()
            await page.wait_for_timeout(2000)

        await self._dismiss_popups(page)
        return True

    async def _open_inbox_conversation(self, page: Page, username: str) -> bool:
        """
        Scan the inbox sidebar for a conversation matching username and click it.
        Tries Playwright locators first, then scrolls the sidebar, then JS fallback.
        Returns True if a match was found and clicked.
        """
        norm = username.lower().replace("_", "")

        async def _try_locators() -> bool:
            for sel in [
                f'[role="listitem"]:has-text("{username}")',
                f'[role="row"]:has-text("{username}")',
                f'a[href*="/direct/t/"]:has-text("{username}")',
                f'li:has-text("{username}")',
            ]:
                loc = page.locator(sel).first
                try:
                    if await loc.count() and await loc.is_visible(timeout=600):
                        await loc.click()
                        await page.wait_for_timeout(2500)
                        return True
                except Exception:
                    pass
            return False

        # First pass — items already visible
        if await _try_locators():
            return True

        # Scroll the sidebar panel up to 4 times to surface the conversation
        for _ in range(4):
            await page.evaluate("""
            () => {
                const s = document.querySelector('[role="complementary"]')
                       || document.querySelector('aside')
                       || document.querySelector('nav');
                if (s) s.scrollTop += 300;
            }
            """)
            await page.wait_for_timeout(500)
            if await _try_locators():
                return True

        # JS fallback — broader text scan on all inbox links
        clicked: bool = await page.evaluate(f"""
        () => {{
            const links = Array.from(document.querySelectorAll(
                'a[href*="/direct/t/"], [role="listitem"], [role="row"], li'
            ));
            const target = '{norm}';
            for (const el of links) {{
                const text = el.textContent.toLowerCase().replace(/_/g, '').replace(/\\s+/g, '');
                if (text.includes(target) || (target.length >= 4 && text.startsWith(target.slice(0, 4)))) {{
                    el.click();
                    return true;
                }}
            }}
            return false;
        }}
        """)
        if clicked:
            await page.wait_for_timeout(2500)
        return clicked

    async def navigate_to_dm(self, page: Page, username: str):
        """Navigate to a specific DM thread."""
        # ── Strategy 1: scan inbox sidebar for existing conversation ─────────
        await page.goto(
            "https://www.instagram.com/direct/inbox/",
            wait_until="domcontentloaded",
        )
        # Wait for the conversation list to actually render (Instagram SPA takes time)
        try:
            await page.wait_for_selector(
                '[role="listitem"], [role="row"], a[href*="/direct/t/"]',
                timeout=8000,
            )
        except PlaywrightTimeoutError:
            pass  # continue and let the sidebar scan handle the empty state
        await page.wait_for_timeout(1500)
        await self._dismiss_popups(page)

        if await self._open_inbox_conversation(page, username):
            await self._dismiss_popups(page)
            print(f"  [nav] Opened DM via inbox sidebar")
            return

        # ── Strategy 2: inbox search bar ─────────────────────────────────────
        for search_sel in [
            'input[placeholder="Search"]',
            'input[placeholder*="Search"]',
            'input[placeholder*="earch"]',
            'input[aria-label*="Search"]',
            'input[aria-label*="earch"]',
            '[role="combobox"]',
        ]:
            search_box = page.locator(search_sel).first
            if await search_box.count():
                try:
                    await search_box.click()
                    await search_box.fill(username)
                    await page.wait_for_timeout(3000)
                    for result_sel in [
                        f'[role="option"]:has-text("{username}")',
                        '[role="option"]',
                        '[role="listbox"] a',
                        f'a:has-text("{username}")',
                        f'[role="listitem"]:has-text("{username}")',
                    ]:
                        result = page.locator(result_sel).first
                        if await result.count():
                            await result.click()
                            await page.wait_for_timeout(3000)
                            if "/direct/t/" in page.url:
                                await self._dismiss_popups(page)
                                print(f"  [nav] Opened DM via inbox search")
                                return
                except Exception:
                    pass
                break

        # ── Strategy 3: profile page → Message button ─────────────────────────
        print(f"  [nav] Trying profile page for @{username}...")
        await page.goto(
            f"https://www.instagram.com/{username}/",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(2500)
        await self._dismiss_popups(page)

        for btn_sel in [
            'button:has-text("Message")',
            '[role="button"]:has-text("Message")',
            'a:has-text("Message")',
        ]:
            btn = page.locator(btn_sel).first
            try:
                if await btn.count() and await btn.is_visible(timeout=1500):
                    await btn.click()
                    await page.wait_for_timeout(3500)
                    if "/direct/t/" in page.url:
                        await self._dismiss_popups(page)
                        print(f"  [nav] Opened DM via profile Message button")
                        return
            except Exception:
                pass

        raise ValueError(
            f"Could not navigate to DM with @{username}. "
            "All three strategies (inbox sidebar, inbox search, profile page) failed."
        )

    # ── Internal helpers (no navigation) ─────────────────────────────────────

    async def _read_from_current_page(
        self,
        page: Page,
        username: str,
        scroll_history: bool = False,
    ) -> list[dict]:
        """
        Extract messages from the currently open DM thread without navigating.

        Uses JavaScript to find message rows and determine sender via horizontal
        position (sent messages appear on the right side of the viewport).
        """
        if scroll_history:
            # Scroll the message container to the top to load older messages
            for _ in range(5):
                await page.evaluate("""
                () => {
                    const c =
                        document.querySelector('[data-scope="messages_table"]') ||
                        document.querySelector('[role="grid"]') ||
                        document.querySelector('[role="list"]') ||
                        document.querySelector('section main');
                    if (c) c.scrollTop = 0;
                }
                """)
                await page.wait_for_timeout(700)

        await page.wait_for_timeout(1000)

        raw: list[dict] = await page.evaluate("""
        () => {
            const results = [];
            const viewWidth = window.innerWidth;

            // Detect the right edge of the sidebar/conversation-list panel dynamically
            const sidebarEl = document.querySelector('[role="complementary"]') ||
                              document.querySelector('aside');
            const leftBoundary = sidebarEl
                ? sidebarEl.getBoundingClientRect().right + 10
                : 370;

            // Slugs that are Instagram pages, not user profiles
            const SKIP_SLUGS = new Set([
                'direct', 'inbox', 'explore', 'reels', 'stories', 'popular',
                'accounts', 'about', 'help', 'press', 'api', 'jobs', 'privacy',
                'terms', 'locations', 'music', 'contact', 'lite', 'threads',
                'create', 'meta',
            ]);

            // Returns true for timestamps, date separators, UI chrome, and reel noise
            function isNoise(text) {
                if (text.length > 200) return false; // long text = real message
                // Absolute timestamps
                if (/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d/.test(text)) return true;
                if (/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\\s+\\d+:\\d+/.test(text)) return true;
                if (/^\\d+:\\d+\\s*(AM|PM)?$/.test(text)) return true;
                // Relative timestamps like "7h", "2d", "1w", "just now", "yesterday"
                if (/^\\d+[smhdw]$/.test(text)) return true;
                if (/^(just now|yesterday|today)$/i.test(text)) return true;
                // Instagram UI chrome
                if (/^Active\\s/.test(text)) return true;
                if (/^©/.test(text)) return true;
                if (/^Seen($|\\s+\\d+|\\s+just now)/.test(text)) return true;
                if (/^(Threads|Help|Privacy|Terms|About|Jobs|Press|API|Locations|Music|Contact|Lite|Meta Verified|Contact Uploading|Non-Users|Messages|Requests|Delivered$|Sent$)/.test(text)) return true;
                // Reel / story share noise
                if (/replied to (you|your story|a story)/i.test(text)) return true;
                if (/reacted to (your|a)/i.test(text)) return true;
                if (/sent you a reel/i.test(text)) return true;
                if (/shared a reel/i.test(text)) return true;
                if (/mentioned you in/i.test(text)) return true;
                // Page title bleed-through like "username · Instagram"
                if (/·\\s*Instagram$/.test(text)) return true;
                // Instagram username slugs bleeding from the sidebar (contain _ or .)
                if (/^[a-z][a-z0-9]*[_.][a-z0-9_.]{1,28}$/.test(text)) return true;
                return false;
            }

            const allNodes = Array.from(document.querySelectorAll('[dir="auto"]'));
            // Use leaf nodes only to avoid nested duplicates
            const nodes = allNodes.filter(n => !n.querySelector('[dir="auto"]'));

            for (const node of nodes) {
                const text = node.textContent.trim();
                if (!text || text.length < 2) continue;

                const rect = node.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                // Skip items in the left sidebar
                if (rect.left < leftBoundary) continue;

                // Skip full-width container wrappers — real message bubbles are
                // narrow; anything spanning more than half the viewport is a row
                if (rect.width > viewWidth * 0.5) continue;

                // Skip if inside nav / header / footer / aside
                let skip = false;
                let el = node.parentElement;
                for (let d = 0; d < 15 && el; d++) {
                    const tag = el.tagName;
                    if (tag === 'NAV' || tag === 'HEADER' || tag === 'FOOTER' || tag === 'ASIDE') {
                        skip = true; break;
                    }
                    el = el.parentElement;
                }
                if (skip) continue;

                // Skip if this node is inside a conversation-list sidebar item
                // (inbox list items contain a /direct/t/ link as a sibling/ancestor)
                let inSidebarItem = false;
                let anc = node.parentElement;
                for (let d = 0; d < 12 && anc; d++) {
                    const role = anc.getAttribute('role');
                    if (role === 'listitem' || anc.tagName === 'LI') {
                        if (anc.querySelector('a[href*="/direct/t/"]')) {
                            inSidebarItem = true; break;
                        }
                    }
                    anc = anc.parentElement;
                }
                if (inSidebarItem) continue;

                // Skip noise (timestamps, footer labels, UI chrome)
                if (isNoise(text)) continue;

                // Sender resolution:
                // 1. Position-based (self = right-aligned, > 60% of viewport)
                // 2. Everything else is 'other' (to be replaced by the target username)
                const midX = rect.left + rect.width / 2;
                let isSelf = midX > viewWidth * 0.6;

                results.push({
                    text,
                    sender: isSelf ? 'self' : 'other',
                    timestamp: new Date().toISOString(),
                });
            }
            return results;
        }
        """)

        # Replace generic 'other' with the known username
        for msg in raw:
            if msg["sender"] == "other":
                msg["sender"] = username

        print(f"  [history] {len(raw)} messages loaded", flush=True)
        if raw:
            senders = set(m["sender"] for m in raw)
            print(f"  [history] Senders: {', '.join(senders)}", flush=True)
            # Log the last 2 messages for better context
            for msg in raw[-2:]:
                print(f"    - {msg['sender']}: {msg['text'][:50]}...", flush=True)
        else:
            # Diagnostic: count dir="auto" nodes so we know if DOM is empty or wrong
            count = await page.evaluate(
                "() => document.querySelectorAll('[dir=\"auto\"]').length"
            )
            print(f"  [debug] 0 messages parsed — {count} [dir=auto] nodes on page", flush=True)
            print(f"  [debug] URL: {page.url}", flush=True)

        return raw

    async def _send_from_current_page(self, page: Page, message: str):
        """Send a message from the currently open DM thread (no navigation)."""
        for sel in [
            'div[aria-label="Message"]',
            'div[role="textbox"]',
            'p[contenteditable="true"]',
            '[contenteditable="true"]',
        ]:
            loc = page.locator(sel)
            if await loc.count():
                box = loc.first
                await box.click()
                await page.wait_for_timeout(300)
                await box.type(message, delay=25)
                await page.wait_for_timeout(200)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)
                return

        raise RuntimeError("Could not find message input box")

    # ── Public methods (navigate + act) ──────────────────────────────────────

    async def read_messages(self, page: Page, username: str) -> list[dict]:
        """Navigate to DM thread and read message history."""
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(2000)
        return await self._read_from_current_page(page, username, scroll_history=True)

    async def send_message(self, page: Page, username: str, message: str):
        """Navigate to DM thread and send a message."""
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(2000)
        await self._send_from_current_page(page, message)
        print(f"✓ Sent to {username}: {message}")

    async def auto_reply(
        self,
        page: Page,
        username: str,
        generator: ReplyGenerator,
        personality: str = "",
    ):
        """Navigate to DM, read history, generate LLM reply — only if THEY sent last message."""
        print(f"\n[instagram] Opening DM with {username}...")
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(2000)

        messages = await self._read_from_current_page(page, username, scroll_history=True)
        print(f"  Loaded {len(messages)} messages")

        if not messages:
            print("  No messages found — cannot reply")
            return

        # Only reply if the other person sent the last message
        last_msg = messages[-1]
        if last_msg["sender"] == "self":
            print(f"  Last message is yours — no need to reply yet")
            return

        their_msgs = [m for m in messages if m["sender"] != "self"]
        if not their_msgs:
            print("  No messages from the other person yet")
            return

        print(f"\n  Last 3 messages:")
        for msg in messages[-3:]:
            label = "You" if msg["sender"] == "self" else msg["sender"]
            print(f"    {label}: {msg['text']}")

        ctx = ConversationContext(username, "instagram", personality)
        for msg in messages:
            ctx.add_message(msg["sender"], msg["text"], msg["timestamp"])

        print(f"\n  Generating reply via LLM...")
        try:
            reply = generator.generate(ctx, platform="instagram", max_length=200)
        except RuntimeError as e:
            if "RATE_LIMITED" in str(e):
                print(f"  [AI] Rate limited{str(e).replace('RATE_LIMITED', '')} — skipping reply")
                return
            raise
        print(f"  Reply: {reply}\n")
        await self._send_from_current_page(page, reply)
        print(f"✓ Sent.")

    async def continuous_auto_reply_loop(
        self,
        page: Page,
        username: str,
        generator: ReplyGenerator,
        check_interval: int = 45,  # kept for API compatibility, not used as sleep
        personality: str = "",
    ):
        """
        Navigate to DM once, then watch the DOM for new message rows.

        Uses Playwright's wait_for_function with a 30-second timeout window so the
        loop stays alive without refreshing the page. Instagram's SPA updates the
        DOM automatically when messages arrive — no polling needed.
        """
        print(f"\n[instagram] Opening DM with {username}...")
        await self.navigate_to_dm(page, username)
        await page.wait_for_timeout(3000)

        # Simple raw count of all [dir="auto"] nodes — any increase means
        # something new appeared (new message or inbox preview update).
        # _read_from_current_page does the real filtering after detection fires.
        _count_js = "() => document.querySelectorAll('[dir=\"auto\"]').length"

        row_count: int = await page.evaluate(_count_js)
        last_replied_text: str | None = None

        print(f"  Ready — {row_count} DOM nodes visible")

        # ── Immediate check: reply to any already-pending message ─────────────
        _init_messages = await self._read_from_current_page(page, username)
        _their = [m for m in _init_messages if m["sender"] != "self"]
        if _their and _init_messages[-1]["sender"] != "self":
            # Last message is theirs — reply right away, don't wait
            _latest = _their[-1]
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] {username}: {_latest['text']}  (pending)")
            _ctx = ConversationContext(username, "instagram", personality)
            for _m in _init_messages[-15:]:
                _ctx.add_message(_m["sender"], _m["text"], _m["timestamp"])
            try:
                _reply = generator.generate(_ctx, platform="instagram", max_length=250)
                print(f"  Sending: {_reply}")
                await self._send_from_current_page(page, _reply)
                last_replied_text = _latest["text"]
                await page.wait_for_timeout(1000)
                row_count = await page.evaluate(_count_js)
                print(f"  Sent.")
            except RuntimeError as _e:
                if "RATE_LIMITED" in str(_e):
                    print(f"  [AI] Rate limited — will retry when next message arrives or timeout")
                    # last_replied_text = _latest["text"]  <-- Removed to allow retry
                else:
                    print(f"  [AI] Error: {_e}")
        else:
            # Last message is ours — remember it so we don't double-reply
            if _their:
                last_replied_text = _their[-1]["text"]

        print(f"\n  Watching for new messages from {username} — Ctrl+C to stop\n")

        while True:
            try:
                # Wait up to 30s for any new [dir="auto"] node; loop on timeout to stay alive
                try:
                    await page.wait_for_function(
                        "(n) => document.querySelectorAll('[dir=\"auto\"]').length > n",
                        arg=row_count,
                        polling=1500,   # DOM check every 1.5 seconds
                        timeout=30000,  # renew the loop every 30s
                    )
                except PlaywrightTimeoutError:
                    continue  # no new node yet — keep waiting

                await page.wait_for_timeout(1200)  # let DOM settle

                messages = await self._read_from_current_page(page, username)
                row_count = await page.evaluate(_count_js)

                if not messages:
                    print(f"  [debug] No messages parsed after DOM change")
                    continue

                # Only reply if their message is actually the last thing in the thread
                latest = messages[-1]
                if latest["sender"] == "self":
                    # We sent the last message, nothing to do
                    print(f"  [skip] Last message is from self: \"{latest['text'][:30]}...\"")
                    continue

                if latest["text"] == last_replied_text:
                    # Already handled this specific message
                    print(f"  [skip] Already replied to: \"{latest['text'][:30]}...\"")
                    continue

                # New message from the other person
                print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] {username}: {latest['text']}")

                ctx = ConversationContext(username, "instagram", personality)
                for msg in messages[-15:]:
                    ctx.add_message(msg["sender"], msg["text"], msg["timestamp"])

                print(f"  Generating reply...")
                try:
                    reply = generator.generate(ctx, platform="instagram", max_length=250)
                except RuntimeError as ai_err:
                    if "RATE_LIMITED" in str(ai_err):
                        print(f"  [AI] Rate limited{str(ai_err).replace('RATE_LIMITED', '')} — will retry later")
                        # last_replied_text = latest["text"]  <-- Removed to allow retry
                        await asyncio.sleep(10) # extra breather
                        continue
                    raise
                print(f"  Sending: {reply}")

                await self._send_from_current_page(page, reply)
                last_replied_text = latest["text"]

                # Update baseline after our sent message added a row
                await page.wait_for_timeout(1000)
                row_count = await page.evaluate(_count_js)

                print(f"  Sent. Watching for next message...\n")

            except KeyboardInterrupt:
                print("\n[instagram] Continuous loop stopped.")
                break
            except Exception as e:
                print(f"  [error] {e} — retrying in 5s")
                await asyncio.sleep(5)


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
            except Exception:
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
        print("  python social_media.py instagram <username> [--auto-reply] [--continuous]")
        print("                                              [--interval N] [--personality '<style>']")
        print("                                              [--model gemini|nvidia|auto]")
        print("  python social_media.py whatsapp  <contact>  [--auto-reply] [--personality '<style>']")
        print("")
        print("Examples:")
        print('  python social_media.py instagram its_ramtamang --auto-reply')
        print('  python social_media.py instagram its_ramtamang --continuous --interval 30')
        print('  python social_media.py instagram its_ramtamang --continuous --model nvidia')
        sys.exit(1)

    platform = sys.argv[1].lower()
    target = sys.argv[2]
    auto_reply = "--auto-reply" in sys.argv
    continuous = "--continuous" in sys.argv
    personality = ""
    interval = 45
    model = "auto"  # gemini | nvidia | auto

    if "--personality" in sys.argv:
        idx = sys.argv.index("--personality")
        if idx + 1 < len(sys.argv):
            personality = sys.argv[idx + 1]

    if "--interval" in sys.argv:
        idx = sys.argv.index("--interval")
        if idx + 1 < len(sys.argv):
            try:
                interval = int(sys.argv[idx + 1])
            except ValueError:
                pass

    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            m = sys.argv[idx + 1].lower()
            if m in ("groq", "gemini", "nvidia", "auto"):
                model = m
            else:
                print(f"  [warn] Unknown --model '{m}', using auto")

    print(f"  [model] {model}")
    generator = ReplyGenerator(personality=personality, model=model)
    memory = SessionMemory()
    memory.load()

    try:
        if platform == "instagram":
            client = InstagramDMClient(headless=False)
            ctx = await client.launch()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            await client.ensure_logged_in(page)

            if continuous:
                await client.continuous_auto_reply_loop(
                    page, target, generator,
                    check_interval=interval,
                    personality=personality,
                )
            elif auto_reply:
                await client.auto_reply(page, target, generator, personality)
            else:
                messages = await client.read_messages(page, target)
                ctx_obj = ConversationContext(target, "instagram", personality)
                for msg in messages:
                    ctx_obj.add_message(msg["sender"], msg["text"], msg["timestamp"])

                # Print full conversation
                print(ctx_obj.get_summary())

                # Feed to AI and print suggested reply
                their_msgs = [m for m in messages if m["sender"] != "self"]
                if their_msgs:
                    print(f"\n{'─'*50}")
                    print(f"  Generating AI reply suggestion...")
                    try:
                        reply = generator.generate(ctx_obj, platform="instagram", max_length=300)
                        print(f"\n  [AI Suggestion]  {reply}")
                    except Exception as ai_err:
                        err_str = str(ai_err)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            import re as _re
                            delay = _re.search(r"retry in (\d+)", err_str)
                            wait = f" (retry in {delay.group(1)}s)" if delay else ""
                            print(f"  [AI] Gemini quota exhausted{wait} — try again later or switch model")
                        else:
                            print(f"  [AI] Generation failed: {ai_err}")
                    print(f"{'─'*50}")

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

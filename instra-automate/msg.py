import asyncio
import sys
from playwright.async_api import async_playwright

async def instagram(username, message):
    async with async_playwright() as p:
        ctx = await p.firefox.launch_persistent_context(
            user_data_dir="./browser_data",
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Check if logged in by looking for the home feed icon (only visible when logged in)
        already_logged_in = await page.query_selector('a[href="/"]') and not await page.query_selector('input[name="username"]')
        if not already_logged_in:
            print(">>> Browser is open. Please log in to Instagram in the browser window.")
            print(">>> Press ENTER here when you are logged in...")
            input()
            await page.wait_for_timeout(2000)

        # Go to DM inbox
        print(f"Opening DMs and searching for '{username}'...")
        await page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        # Click compose/new message button if search box not visible
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
        await page.locator('input[placeholder*="Search"]').first.click()
        await page.locator('input[placeholder*="Search"]').first.fill(username)
        await page.wait_for_timeout(2500)
        await page.screenshot(path="debug.png")

        # Click first matching result
        result = page.locator(f'span:has-text("{username}")').first
        if await result.count():
            await result.click()
            await page.wait_for_timeout(2000)
        else:
            print(f"No result for '{username}' — check debug.png")
            await ctx.close()
            return

        # Click Next/Chat button if present
        for label in ["Next", "Chat"]:
            btn = page.locator(f'div[role="button"]:has-text("{label}")')
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(2000)
                break

        await page.wait_for_timeout(3000)
        await page.screenshot(path="debug2.png")

        # Find message input using locator (resilient to DOM changes)
        box = None
        for sel in ['div[aria-label="Message"]', 'div[role="textbox"]', 'p[contenteditable="true"]']:
            loc = page.locator(sel)
            if await loc.count():
                box = loc.first
                print(f"Found message box: {sel}")
                break

        if box:
            await box.click()
            await page.wait_for_timeout(500)
            await box.type(message, delay=50)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
            print(f"Sent to '{username}': {message}")
        else:
            print("Could not find message box — check debug2.png")

        await page.wait_for_timeout(3000)
        await ctx.close()

async def whatsapp(name, message):
    async with async_playwright() as p:
        ctx = await p.firefox.launch_persistent_context(
            user_data_dir="./browser_data_whatsapp",
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")

        print("Waiting for WhatsApp to load (scan QR if first time)...")
        await page.wait_for_selector('div[role="textbox"]', timeout=60000)
        await page.wait_for_timeout(2000)

        # Search for contact
        search = await page.query_selector('div[contenteditable="true"][title="Search input textbox"]') or \
                 await page.query_selector('div[role="textbox"]')
        await search.click()
        await search.type(name, delay=50)
        await page.wait_for_timeout(2000)

        contact = await page.query_selector(f'span[title="{name}"]')
        if contact:
            await contact.click()
        else:
            print(f"Contact '{name}' not found.")
            await ctx.close()
            return

        await page.wait_for_timeout(2000)
        msg_box = await page.query_selector('div[contenteditable="true"][title="Type a message"]')
        if msg_box:
            await msg_box.click()
            await msg_box.type(message, delay=50)
            await page.keyboard.press("Enter")
            print(f"Sent to {name}: {message}")
        else:
            print("Could not find message box.")

        await page.wait_for_timeout(3000)
        await ctx.close()

def usage():
    print("Usage:")
    print("  python3 msg.py instagram <username> <message>")
    print("  python3 msg.py whatsapp  <name>     <message>")
    print()
    print("Examples:")
    print('  python3 msg.py instagram its_ramtamang "Hey!"')
    print('  python3 msg.py whatsapp  "Ram Tamang"  "Hey!"')

if __name__ == "__main__":
    if len(sys.argv) < 4:
        usage()
        sys.exit(1)

    platform = sys.argv[1].lower()
    target   = sys.argv[2]
    message  = sys.argv[3]

    if platform == "instagram":
        asyncio.run(instagram(target, message))
    elif platform == "whatsapp":
        asyncio.run(whatsapp(target, message))
    else:
        print(f"Unknown platform: {platform}")
        usage()

import asyncio
from playwright.async_api import async_playwright

TARGET_USER = "its_ramtamang"
MESSAGE = "Hello from automation! 👋"
COOKIES_FILE = "instagram_cookies.json"

async def main():
    async with async_playwright() as p:
        # Launch visible Firefox with persistent storage
        ctx = await p.firefox.launch_persistent_context(
            user_data_dir="./browser_data",
            headless=False,
            viewport={"width": 1280, "height": 800},
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print("Opening Instagram...")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Check if already logged in
        if "login" in page.url or await page.query_selector('input[name="username"]'):
            print("Not logged in. Please log in manually in the browser window.")
            print("Waiting up to 60 seconds for login...")
            await page.wait_for_url("https://www.instagram.com/", timeout=60000)
            await page.wait_for_timeout(2000)

        print(f"Navigating to {TARGET_USER}'s profile...")
        await page.goto(f"https://www.instagram.com/{TARGET_USER}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Click "Message" button on profile
        print("Looking for Message button...")
        msg_btn = await page.query_selector('div[role="button"]:has-text("Message")')
        if not msg_btn:
            # Try alternate selector
            msg_btn = await page.query_selector('button:has-text("Message")')

        if msg_btn:
            await msg_btn.click()
            print("Clicked Message button.")
        else:
            print("Message button not found. Opening DMs directly...")
            await page.goto("https://www.instagram.com/direct/new/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            search = await page.query_selector('input[placeholder*="Search"]')
            if search:
                await search.type(TARGET_USER)
                await page.wait_for_timeout(2000)
                result = await page.query_selector(f'span:has-text("{TARGET_USER}")')
                if result:
                    await result.click()
                    await page.wait_for_timeout(1000)
                    next_btn = await page.query_selector('div[role="button"]:has-text("Next")')
                    if next_btn:
                        await next_btn.click()

        await page.wait_for_timeout(3000)

        # Type and send message
        print("Typing message...")
        msg_box = await page.query_selector('div[role="textbox"][aria-label*="essage"]')
        if not msg_box:
            msg_box = await page.query_selector('div[contenteditable="true"]')

        if msg_box:
            await msg_box.click()
            await msg_box.type(MESSAGE, delay=50)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
            print(f"Message sent to {TARGET_USER}!")
        else:
            print("Could not find message input box.")

        print("Done. Browser will stay open for 5 seconds...")
        await page.wait_for_timeout(5000)
        await ctx.close()

asyncio.run(main())

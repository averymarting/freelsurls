import asyncio, json, os, re, sys
from playwright.async_api import async_playwright

PAGE_URL = os.getenv("PAGE_URL", "https://www.facebook.com/profile.php?id=61596271422824")
MAX_SCROLLS = int(os.getenv("MAX_SCROLLS", "60"))
STATE_FILE = "fb_state.json"          # optional logged-in session (from secret)
OUT_TXT, OUT_JSON = "reels_urls.txt", "reels_urls.json"
REEL_RE = re.compile(r"/reel/(\d+)")


async def dismiss_popups(page):
    for _ in range(2):
        try:
            await page.keyboard.press("Escape")
            btn = page.locator('[aria-label="Close"], [aria-label="Decline optional cookies"]').first
            if await btn.count():
                await btn.click(timeout=1500)
        except Exception:
            pass
        await page.wait_for_timeout(500)


async def collect(page):
    hrefs = await page.eval_on_selector_all(
        'a[href*="/reel/"]', "els => els.map(e => e.getAttribute('href'))"
    )
    ids = []
    for h in hrefs:
        m = REEL_RE.search(h or "")
        if m:
            ids.append(m.group(1))
    return ids


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx_args = dict(
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        if os.path.exists(STATE_FILE):
            ctx_args["storage_state"] = STATE_FILE
            print("Using saved login session")
        ctx = await browser.new_context(**ctx_args)
        page = await ctx.new_page()

        await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await dismiss_popups(page)

        # Click the Reels tab; fall back to direct URL
        try:
            await page.get_by_role("tab", name="Reels").click(timeout=10000)
        except Exception:
            print("Tab click failed, opening reels_tab URL directly")
            sep = "&" if "?" in PAGE_URL else "?"
            await page.goto(f"{PAGE_URL}{sep}sk=reels_tab", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await dismiss_popups(page)

        seen, stale = {}, 0
        for i in range(MAX_SCROLLS):
            for rid in await collect(page):
                seen.setdefault(rid, f"https://www.facebook.com/reel/{rid}")
            print(f"scroll {i+1}: {len(seen)} reels")
            before = len(seen)
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)
            for rid in await collect(page):
                seen.setdefault(rid, f"https://www.facebook.com/reel/{rid}")
            stale = stale + 1 if len(seen) == before else 0
            if stale >= 5:
                print("No new reels after 5 scrolls, stopping")
                break

        await page.screenshot(path="debug.png")
        await browser.close()

    urls = list(seen.values())
    with open(OUT_TXT, "w") as f:
        f.write("\n".join(urls))
    with open(OUT_JSON, "w") as f:
        json.dump(urls, f, indent=2)
    print(f"Saved {len(urls)} reel URLs")
    if not urls:
        sys.exit(1)


asyncio.run(main())

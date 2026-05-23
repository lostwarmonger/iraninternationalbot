import os
import time
import logging
import asyncio
from playwright.async_api import async_playwright
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def parse_cookie_string(cookie_str: str) -> list[dict]:
    """Parse YouTube cookie string into Playwright format."""
    cookies = []
    for item in cookie_str.split(';'):
        if '=' not in item:
            continue
        name, value = item.split('=', 1)
        name, value = name.strip(), value.strip()
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "httpOnly": name in ["LOGIN_INFO", "SID", "__Secure-1PSID", "__Secure-3PSID", "HSID", "SSID"],
        })
    return cookies

async def capture_youtube_screenshot(url: str, cookies: list[dict], output_path: str = "snapshot.jpg") -> bool:
    """Capture YouTube live with proper styles and 16:9 aspect ratio."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--mute-audio",
                ]
            )
            
            # 👇 KEY: Proper 16:9 viewport
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},  # 16:9 ratio
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="Asia/Tehran",
            )
            
            if cookies:
                await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # 👇 KEY: Only block heavy/unneeded resources — ALLOW STYLESHEETS
            await page.route("**/*", lambda route: 
                route.abort() if route.request.resource_type in ["image", "font", "csp_report", "websocket", "media"] 
                else route.continue_()
            )
            
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Wait for player + let styles apply
            logger.info("⏳ Waiting for player and styles...")
            await page.wait_for_selector(".html5-video-player", timeout=20000)
            await asyncio.sleep(4)  # Let CSS/rendering complete
            
            # 👇 KEY: Screenshot the player container with exact 16:9 crop
            try:
                player = await page.query_selector(".html5-video-player")
                if player:
                    # Get player bounds
                    bounds = await player.bounding_box()
                    if bounds:
                        # Crop to 16:9 area within player (avoid UI overlays)
                        clip = {
                            "x": bounds["x"] + 10,
                            "y": bounds["y"] + 10,
                            "width": min(bounds["width"] - 20, 1280),
                            "height": min(bounds["height"] - 20, 720),
                        }
                        # Ensure 16:9 ratio
                        if clip["width"] / clip["height"] > 16/9:
                            clip["width"] = clip["height"] * 16/9
                        else:
                            clip["height"] = clip["width"] * 9/16
                            
                        logger.info(f"🎬 Screenshotting player area: {clip['width']}x{clip['height']}")
                        await page.screenshot(path=output_path, clip=clip)
                    else:
                        # Fallback: full viewport screenshot
                        await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
                else:
                    # Fallback: full viewport
                    await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
            except Exception as e:
                logger.warning(f"⚠️ Player screenshot failed, using fallback: {e}")
                await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
            
            logger.info(f"✅ Screenshot saved: {output_path}")
            await browser.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ Capture failed: {e}")
        return False

async def send_photo_to_telegram(bot_token: str, chat_id: str, photo_path: str) -> bool:
    try:
        bot = Bot(token=bot_token)
        with open(photo_path, "rb") as photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=f"🔴 Live • {time.strftime('%H:%M:%S')}",
                read_timeout=30,
            )
        logger.info("✅ Photo sent to Telegram.")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")
        return False

async def main():
    logger.info("🚀 Starting snapshot task...")
    
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    youtube_url = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
    cookie_str = os.environ.get("YOUTUBE_COOKIES", "")
    
    if not bot_token or not chat_id:
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID")
        exit(1)
    
    cookies = parse_cookie_string(cookie_str) if cookie_str else []
    
    success = await capture_youtube_screenshot(youtube_url, cookies, "snapshot.jpg")
    if not success:
        logger.error("❌ Failed to capture screenshot")
        exit(1)
    
    sent = await send_photo_to_telegram(bot_token, chat_id, "snapshot.jpg")
    if not sent:
        logger.error("❌ Failed to send photo")
        exit(1)
    
    logger.info("🎉 Task complete!")
    exit(0)

if __name__ == "__main__":
    asyncio.run(main())

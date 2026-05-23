import os
import io
import time
import logging
import asyncio
import json
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
    # Add required base cookies if missing
    base_cookies = [
        {"name": "PREF", "value": "f4=4000000&f6=40000000", "domain": ".youtube.com", "path": "/", "secure": True, "httpOnly": False},
        {"name": "VISITOR_INFO1_LIVE", "value": "live", "domain": ".youtube.com", "path": "/", "secure": True, "httpOnly": False},
    ]
    for bc in base_cookies:
        if not any(c["name"] == bc["name"] for c in cookies):
            cookies.append(bc)
    return cookies

async def capture_youtube_with_cookies(url: str, cookies: list[dict], output_path: str = "snapshot.jpg") -> bool:
    """Open YouTube with auth cookies and screenshot the video player."""
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
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="Asia/Tehran",
            )
            
            # 👇 KEY: Add your cookies to authenticate the session
            await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # Block non-essential resources to speed up load
            await page.route("**/*", lambda route: 
                route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "csp_report", "websocket"] 
                else route.continue_()
            )
            
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Wait for video player + video element
            logger.info("⏳ Waiting for video player...")
            await page.wait_for_selector(".html5-video-player, video", timeout=20000)
            await asyncio.sleep(3)  # Let stream initialize
            
            # Try to find and screenshot the <video> element directly
            try:
                video = await page.query_selector("video")
                if video:
                    logger.info("🎬 Screenshotting <video> element...")
                    await video.screenshot(path=output_path)
                else:
                    logger.info("🎬 Screenshotting player container...")
                    player = await page.query_selector(".html5-video-player")
                    if player:
                        await player.screenshot(path=output_path)
                    else:
                        await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
            except Exception as e:
                logger.warning(f"⚠️ Element screenshot failed, falling back: {e}")
                await page.screenshot(path=output_path, full_page=False)
            
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
    logger.info("🚀 Starting authenticated snapshot task...")
    
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    youtube_url = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
    cookie_str = os.environ.get("YOUTUBE_COOKIES", "")
    
    if not bot_token or not chat_id:
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID")
        exit(1)
    
    if not cookie_str:
        logger.warning("⚠️ No YOUTUBE_COOKIES provided — may get blocked by YouTube")
    
    # Parse cookies
    cookies = parse_cookie_string(cookie_str) if cookie_str else []
    
    # Capture screenshot
    success = await capture_youtube_with_cookies(youtube_url, cookies, "snapshot.jpg")
    if not success:
        logger.error("❌ Failed to capture screenshot")
        exit(1)
    
    # Send to Telegram
    sent = await send_photo_to_telegram(bot_token, chat_id, "snapshot.jpg")
    if not sent:
        logger.error("❌ Failed to send photo")
        exit(1)
    
    logger.info("🎉 Task complete!")
    exit(0)

if __name__ == "__main__":
    asyncio.run(main())

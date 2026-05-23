import os
import time
import logging
import asyncio
from datetime import datetime
import pytz
from playwright.async_api import async_playwright
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def get_tehran_time() -> str:
    """Return current time in Tehran formatted as HH:MM:SS"""
    tehran = pytz.timezone("Asia/Tehran")
    return datetime.now(tehran).strftime("%H:%M:%S")

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

async def capture_youtube_fullpage(url: str, cookies: list[dict], output_path: str = "snapshot.jpg") -> bool:
    """Capture YouTube live with full page (video + comments) and proper Tehran time."""
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
            
            # 👇 Larger viewport to show video + comments side-by-side
            context = await browser.new_context(
                viewport={"width": 1400, "height": 900},  # Wider to fit video + comments
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="Asia/Tehran",  # 👈 Helps YouTube show correct regional content
            )
            
            if cookies:
                await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # 👇 Allow stylesheets + essential resources (block only heavy stuff)
            await page.route("**/*", lambda route: 
                route.abort() if route.request.resource_type in ["font", "csp_report", "websocket"] 
                else route.continue_()
            )
            
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Wait for player + let page fully render
            logger.info("⏳ Waiting for page to render...")
            await page.wait_for_selector(".html5-video-player", timeout=20000)
            await asyncio.sleep(5)  # Let comments/UI load
            
            # 👇 KEY: Full viewport screenshot (no crop) - shows video + comments
            logger.info("📸 Taking full viewport screenshot...")
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
        # 👇 Use Tehran time in caption
        tehran_time = get_tehran_time()
        with open(photo_path, "rb") as photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=f"🔴 Live • {tehran_time}",
                read_timeout=30,
            )
        logger.info(f"✅ Photo sent to Telegram (Tehran time: {tehran_time})")
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
    
    success = await capture_youtube_fullpage(youtube_url, cookies, "snapshot.jpg")
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

import os
import io
import time
import logging
import asyncio
from playwright.async_api import async_playwright
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

async def capture_youtube_screenshot(url: str, output_path: str = "snapshot.jpg") -> bool:
    """Open YouTube in headless browser and screenshot the video player."""
    try:
        async with async_playwright() as p:
            # Launch browser with realistic settings to avoid detection
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                ]
            )
            
            # Create context with realistic viewport & user agent
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Navigate to YouTube
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="networkidle", timeout=50000)
            
            # Wait for video player to load (look for common player elements)
            try:
                await page.wait_for_selector("video, .html5-video-player, ytd-player", timeout=50000)
                # Extra wait for live stream to initialize
                await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"⚠️ Player selector not found, proceeding anyway: {e}")
            
            # Take screenshot of entire page
            await page.screenshot(path=output_path, full_page=False)
            logger.info(f"✅ Screenshot saved to {output_path}")
            
            await browser.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ Screenshot failed: {e}")
        return False

async def send_photo_to_telegram(bot_token: str, chat_id: str, photo_path: str) -> bool:
    """Send the screenshot to Telegram."""
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
    logger.info("🚀 Starting Playwright snapshot task...")
    
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    youtube_url = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
    
    if not bot_token or not chat_id:
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID in secrets")
        exit(1)
    
    # 1. Capture screenshot
    success = await capture_youtube_screenshot(youtube_url, "snapshot.jpg")
    if not success:
        logger.error("❌ Failed to capture screenshot")
        exit(1)
    
    # 2. Send to Telegram
    sent = await send_photo_to_telegram(bot_token, chat_id, "snapshot.jpg")
    if not sent:
        logger.error("❌ Failed to send photo")
        exit(1)
    
    logger.info("🎉 Task complete!")
    exit(0)

if __name__ == "__main__":
    asyncio.run(main())

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
    """Capture screenshot of YouTube live stream with optimized loading."""
    try:
        async with async_playwright() as p:
            # Launch browser with anti-detection flags
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # 👇 KEY FIX: Use lighter wait condition + longer timeout
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for video player specifically (not entire page)
            try:
                logger.info("⏳ Waiting for video player...")
                await page.wait_for_selector("video, .html5-video-player", timeout=20000)
                await asyncio.sleep(2)  # Let stream buffer slightly
                logger.info("✅ Video player ready")
            except Exception as e:
                logger.warning(f"⚠️ Player wait timed out, proceeding anyway: {e}")
                await asyncio.sleep(3)  # Fallback wait
            
            # Optional: Hide YouTube UI overlays for cleaner screenshot
            await page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('.ytp-chrome-bottom, .ytp-gradient-bottom, .ytp-bigmode');
                    elements.forEach(el => el.style.display = 'none');
                }
            """)
            
            # Take screenshot
            await page.screenshot(path=output_path, full_page=False)
            logger.info(f"✅ Screenshot saved: {output_path}")
            
            await browser.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ Screenshot failed: {e}")
        return False

async def send_photo_to_telegram(bot_token: str, chat_id: str, photo_path: str) -> bool:
    """Send screenshot to Telegram."""
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
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID")
        exit(1)
    
    # Capture screenshot
    success = await capture_youtube_screenshot(youtube_url, "snapshot.jpg")
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

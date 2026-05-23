import os
import io
import time
import logging
import asyncio
import random
from playwright.async_api import async_playwright
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

async def capture_youtube_video_element(url: str, output_path: str = "snapshot.jpg") -> bool:
    """Capture ONLY the video element from YouTube, bypassing overlays."""
    try:
        async with async_playwright() as p:
            # Launch with maximum stealth
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--mute-audio",  # No sound needed
                ]
            )
            
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
                permissions=["geolocation"],
            )
            
            # 👇 Fake geolocation to look more human
            await context.grant_permissions(["geolocation"])
            await context.set_geolocation({"latitude": 40.7128, "longitude": -74.0060})
            
            page = await context.new_page()
            
            # 👇 Block unnecessary resources to speed up load + reduce detection surface
            await page.route("**/*", lambda route: 
                route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "csp_report"] 
                else route.continue_()
            )
            
            logger.info(f"🌐 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for video element specifically
            logger.info("⏳ Waiting for <video> element...")
            try:
                video = await page.wait_for_selector("video", timeout=25000)
                await asyncio.sleep(random.uniform(2, 4))  # Human-like delay
                
                # 👇 KEY: Screenshot ONLY the video element (ignores overlays)
                logger.info("🎬 Screenshotting video element only...")
                await video.screenshot(path=output_path)
                logger.info(f"✅ Video element screenshot saved: {output_path}")
                
            except Exception as e:
                logger.error(f"❌ Could not find or screenshot video element: {e}")
                # Fallback: try full page screenshot with overlay removal attempt
                await page.evaluate("""
                    () => {
                        // Try to hide common YouTube overlays
                        document.querySelectorAll('.ytp-ce-element, .ytp-pause-overlay, .ytp-chrome-bottom, .yt-simple-endpoint, .yt-spec-button-shape-next').forEach(el => el.style.display = 'none');
                    }
                """)
                await asyncio.sleep(2)
                await page.screenshot(path=output_path, full_page=False)
                logger.info("✅ Fallback full-page screenshot taken")
            
            await browser.close()
            return True
            
    except Exception as e:
        logger.error(f"❌ Browser task failed: {e}")
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
    logger.info("🚀 Starting stealth snapshot task...")
    
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    youtube_url = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
    
    if not bot_token or not chat_id:
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID")
        exit(1)
    
    # Capture video element screenshot
    success = await capture_youtube_video_element(youtube_url, "snapshot.jpg")
    if not success:
        logger.error("❌ Failed to capture video")
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

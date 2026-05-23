import os
import io
import time
import logging
import asyncio
import ffmpeg
from yt_dlp import YoutubeDL
from telegram import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def get_stream_url(url):
    """Get direct stream URL with anti-bot bypass options."""
    try:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "dump_single_json": True,
            # 👇 These options help bypass YouTube's bot detection
            "extractor_args": {
                "youtube": {
                    "player_client": "web,ios",  # Try multiple player clients
                    "skip": "dash,ytbp",          # Skip formats that often require auth
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            "socket_timeout": 20,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Try multiple fallback fields for the stream URL
            stream_url = (
                info.get("url") or 
                info.get("formats", [{}])[-1].get("url") or
                info.get("hls_manifest_url") or
                info.get("dash_manifest_url")
            )
            if stream_url:
                logger.info(f"✅ Got stream URL (format: {info.get('format', 'unknown')})")
            return stream_url
    except Exception as e:
        logger.error(f"❌ Failed to get stream URL: {e}")
        return None

def capture_frame(stream_url):
    """Grab one frame from the live stream."""
    try:
        out, _ = (
            ffmpeg
            .input(stream_url, {"timeout": 20, "rtmp_live": "live"})
            .output("pipe:", format="image2", vframes=1, update=1)
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        image_bytes = out.stdout.read()
        out.wait()
        if image_bytes and len(image_bytes) > 1000:  # Basic sanity check
            logger.info(f"✅ Frame captured ({len(image_bytes)} bytes)")
            return image_bytes
        logger.warning("⚠️ Frame too small or empty")
        return None
    except Exception as e:
        logger.error(f"❌ FFmpeg capture failed: {e}")
        return None

async def send_to_telegram(bot, chat_id, image_bytes):
    """Send captured frame to Telegram."""
    try:
        photo_buffer = io.BytesIO(image_bytes)
        photo_buffer.name = "live_snapshot.jpg"
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo_buffer,
            caption=f"🔴 Live • {time.strftime('%H:%M:%S')}",
            read_timeout=30,
        )
        logger.info("✅ Photo sent successfully.")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")
        return False

async def main():
    logger.info("🚀 Starting snapshot task...")
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    youtube_url = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")

    if not bot_token or not chat_id:
        logger.error("❌ Missing BOT_TOKEN or CHAT_ID")
        exit(1)

    # 1. Get stream URL (with retries)
    for attempt in range(3):
        stream_url = get_stream_url(youtube_url)
        if stream_url:
            break
        logger.warning(f"⚠️ Retry {attempt+1}/3 for stream URL...")
        await asyncio.sleep(5)
    
    if not stream_url:
        logger.error("❌ No stream URL after retries. Exiting.")
        exit(1)

    # 2. Capture frame (with retries)
    for attempt in range(3):
        frame = capture_frame(stream_url)
        if frame:
            break
        logger.warning(f"⚠️ Retry {attempt+1}/3 for frame capture...")
        await asyncio.sleep(3)
    
    if not frame:
        logger.error("❌ Frame capture failed after retries. Exiting.")
        exit(1)

    # 3. Send to Telegram
    bot = Bot(token=bot_token)
    success = await send_to_telegram(bot, chat_id, frame)
    
    if success:
        logger.info("🎉 Task complete.")
        exit(0)
    else:
        logger.error("❌ Failed to send. Exiting.")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())

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
    try:
        ydl_opts = {"format": "best[ext=mp4]/best", "quiet": True, "no_warnings": True, "dump_single_json": True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url") or info.get("formats", [{}])[-1].get("url")
    except Exception as e:
        logger.error(f"❌ Failed to get stream URL: {e}")
        return None

def capture_frame(stream_url):
    try:
        out, _ = (
            ffmpeg.input(stream_url, {"timeout": 15})
            .output("pipe:", format="image2", vframes=1, update=1)
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        image_bytes = out.stdout.read()
        out.wait()
        return image_bytes if len(image_bytes) > 0 else None
    except Exception as e:
        logger.error(f"❌ FFmpeg capture failed: {e}")
        return None

async def send_to_telegram(bot, chat_id, image_bytes):
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

    stream_url = get_stream_url(youtube_url)
    if not stream_url:
        logger.error("❌ No stream URL found. Exiting.")
        exit(1)

    frame = capture_frame(stream_url)
    if not frame:
        logger.error("❌ Frame capture failed. Exiting.")
        exit(1)

    bot = Bot(token=bot_token)
    await send_to_telegram(bot, chat_id, frame)
    logger.info("🎉 Task complete.")

if __name__ == "__main__":
    asyncio.run(main())

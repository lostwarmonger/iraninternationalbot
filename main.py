import os
import io
import sys
import time
import logging
import asyncio
import threading
from flask import Flask, jsonify

import ffmpeg
from yt_dlp import YoutubeDL
from telegram import Bot

# ================= CONFIGURATION =================
# These will be automatically filled by Render Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
YOUTUBE_URL = os.environ.get("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
CAPTURE_INTERVAL = int(os.environ.get("CAPTURE_INTERVAL", "180"))  # 180s = 3 minutes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

if not BOT_TOKEN or not CHAT_ID:
    logger.warning("⚠️ BOT_TOKEN or CHAT_ID missing. Set them in Render dashboard.")

# ================= CORE FUNCTIONS =================
def get_stream_url(url):
    """Extract direct streaming URL from YouTube."""
    try:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            "dump_single_json": True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url") or info.get("formats", [{}])[-1].get("url")
    except Exception as e:
        logger.error(f"❌ Failed to get stream URL: {e}")
        return None

def capture_frame(stream_url):
    """Grab one frame from the live stream."""
    try:
        out, _ = (
            ffmpeg
            .input(stream_url, {"timeout": 15})
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

async def run_task():
    """Main workflow: get URL → capture → send → exit."""
    logger.info("🚀 Starting snapshot task...")
    
    stream_url = get_stream_url(YOUTUBE_URL)
    if not stream_url:
        logger.error("❌ No stream URL. Task skipped.")
        return False

    frame = capture_frame(stream_url)
    if not frame:
        logger.error("❌ No frame captured. Task skipped.")
        return False

    bot = Bot(token=BOT_TOKEN)
    success = await send_to_telegram(bot, CHAT_ID, frame)
    return success

# ================= FLASK WEB SERVER =================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "alive"}), 200

@app.route("/trigger", methods=["GET", "POST"])
def trigger():
    """Webhook to run the task."""
    logger.info("📥 Trigger received. Running task...")
    def run_async():
        asyncio.run(run_task())
    threading.Thread(target=run_async, daemon=True).start()
    return jsonify({"status": "triggered"}), 200

def start_flask():
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, use_reloader=False)

# ================= MAIN =================
if __name__ == "__main__":
    # If run locally: just execute task once for testing
    if not os.environ.get("RENDER"):
        logger.info("💻 Running locally. Executing task once...")
        asyncio.run(run_task())
        sys.exit()

    # If on Render: keep Flask alive, wait for /trigger pings
    logger.info("🖥️ Render mode: Web server active, waiting for triggers...")
    start_flask()
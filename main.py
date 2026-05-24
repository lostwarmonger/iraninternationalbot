#!/usr/bin/env python3
"""
YouTube Live Screenshot - Daemon Mode (Cropped + systemd ready)
- Uses system Chromium with anti-detection
- Auto-play + scroll for comments
- Crops to video+comments area only (1270x714)
- Prevents duplicate sends
- Tehran time in caption
"""
import os, sys, logging, time, subprocess, json, hashlib
from datetime import datetime
from pathlib import Path

import pytz
from dotenv import load_dotenv
from telegram import Bot
from PIL import Image

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("snapshot.log", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ========== تنظیمات ==========
TEHRAN_TZ = pytz.timezone("Asia/Tehran")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "180"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "screenshots")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH", "/usr/bin/chromium-browser")
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

# ========== تنظیمات برش تصویر ==========
# ابعاد ناحیه ویدیو + کامنت‌ها
CROP_ENABLED = os.getenv("CROP_ENABLED", "true").lower() == "true"
CROP_X = int(os.getenv("CROP_X", "0"))           # شروع افقی (چپ)
CROP_Y = int(os.getenv("CROP_Y", "55"))          # شروع عمودی (پایین‌تر از هدر)
CROP_WIDTH = int(os.getenv("CROP_WIDTH", "1270"))  # عرض ناحیه هدف
CROP_HEIGHT = int(os.getenv("CROP_HEIGHT", "714")) # ارتفاع ناحیه هدف

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def get_tehran_time() -> str:
    return datetime.now(TEHRAN_TZ).strftime("%H:%M:%S")

def get_timestamp() -> str:
    return datetime.now(TEHRAN_TZ).strftime("%Y%m%d_%H%M%S")

def parse_cookies(cookie_str: str) -> list[str]:
    cookies = []
    for item in cookie_str.split(';'):
        if '=' not in item: continue
        name, value = item.split('=', 1)
        name, value = name.strip(), value.strip()
        if not name or not value: continue
        cookies.append(f"{name}={value}")
    return cookies

def file_hash(filepath: str) -> str:
    if not Path(filepath).exists():
        return ""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def crop_image(input_path: str, output_path: str) -> bool:
    """برش تصویر به ناحیه ویدیو + کامنت‌ها"""
    try:
        with Image.open(input_path) as img:
            width, height = img.size
            
            # محاسبه مختصات برش با بررسی مرزها
            left = max(0, min(CROP_X, width - 1))
            top = max(0, min(CROP_Y, height - 1))
            right = min(left + CROP_WIDTH, width)
            bottom = min(top + CROP_HEIGHT, height)
            
            # اگر ناحیه برش معتبر است
            if right <= left or bottom <= top:
                logger.warning(f"⚠️ Invalid crop bounds: {left},{top},{right},{bottom} | Image: {width}x{height}")
                return False
            
            cropped = img.crop((left, top, right, bottom))
            cropped.save(output_path, quality=95, optimize=True)
            logger.info(f"✂️ Cropped: {input_path} → {output_path} ({CROP_WIDTH}x{CROP_HEIGHT})")
            return True
    except Exception as e:
        logger.error(f"❌ Crop failed: {e}")
        return False

def take_screenshot(url: str, cookies: list[str], output: str) -> bool:
    """اسکرین‌شات با کرومیوم سیستم + تزریق جاوااسکریپت"""
    try:
        # فایل جاوااسکریپت برای تعامل با صفحه
        js_file = "/tmp/youtube_inject.js"
        with open(js_file, "w", encoding="utf-8") as f:
            f.write("""
// Wait for player and auto-play
setTimeout(() => {
    const player = document.querySelector('.html5-video-player');
    if (player) {
        const video = player.querySelector('video');
        if (video && video.paused) {
            video.play().catch(()=>{});
            const overlay = player.querySelector('.ytp-large-play-button');
            if (overlay) overlay.style.display = 'none';
        }
    }
    // Scroll to trigger comments lazy-load
    window.scrollTo(0, document.body.scrollHeight);
    setTimeout(() => window.scrollTo(0, 800), 1500);
}, 3000);
setTimeout(() => console.log('Page ready'), 8000);
            """)
        
        cookie_file = None
        if cookies:
            cookie_file = "/tmp/cookies.txt"
            with open(cookie_file, "w") as f:
                for c in cookies:
                    f.write(f"{c}\n")
        
        cmd = [
            CHROMIUM_PATH,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--mute-audio",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--user-agent={USER_AGENT}",
            "--window-size=1400,900",
            "--virtual-time-budget=12000",
            f"--execute-script={js_file}",
            f"--screenshot={output}",
        ]
        
        if cookie_file:
            cmd.append(f"--cookie-file={cookie_file}")
        cmd.append(url)
        
        logger.info(f"🌐 Capturing: {url}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            logger.error(f"❌ Chromium error: {result.stderr[:300]}")
            return False
        
        if Path(output).exists() and Path(output).stat().st_size > 5000:
            logger.info(f"✅ Raw screenshot saved: {output}")
            return True
        else:
            logger.error("❌ Screenshot file is empty or too small")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Screenshot timed out")
        return False
    except Exception as e:
        logger.error(f"❌ Capture failed: {e}")
        return False
    finally:
        for f in ["/tmp/youtube_inject.js", "/tmp/cookies.txt"]:
            if Path(f).exists():
                Path(f).unlink(missing_ok=True)

async def send_telegram(bot_token: str, chat_id: str, photo: str, last_hash: str) -> tuple[bool, str]:
    try:
        current_hash = file_hash(photo)
        if current_hash == last_hash and last_hash:
            logger.info("⚠️ Same screenshot, skipping send")
            return False, current_hash
        
        bot = Bot(token=bot_token)
        with open(photo, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=f"🔴 Live • {get_tehran_time()}",
                read_timeout=30
            )
        logger.info("✅ Sent to Telegram")
        return True, current_hash
    except Exception as e:
        logger.error(f"❌ Telegram failed: {e}")
        return False, file_hash(photo)

def cleanup_old_screenshots(directory: str, keep: int = 10):
    files = sorted(Path(directory).glob("snapshot_*.jpg"), key=lambda p: p.stat().st_mtime)
    for old in files[:-keep]:
        try:
            old.unlink()
            logger.info(f"🗑️ Deleted old: {old.name}")
        except:
            pass

def main_loop():
    logger.info("🚀 Starting cropped daemon mode...")
    
    bot_token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    url = os.getenv("YOUTUBE_URL", "https://www.youtube.com/watch?v=5JDxjsAVaGk")
    cookies_str = os.getenv("YOUTUBE_COOKIES", "")
    
    if not bot_token or not chat_id:
        logger.error("❌ BOT_TOKEN or CHAT_ID missing")
        return
    
    cookies = parse_cookies(cookies_str) if cookies_str else []
    last_sent_hash = None
    
    logger.info(f"⏱ Interval: {INTERVAL_SECONDS}s | Crop: {CROP_WIDTH}x{CROP_HEIGHT}@{CROP_X},{CROP_Y}")
    
    while True:
        try:
            start = time.time()
            timestamp = get_timestamp()
            
            raw_path = os.path.join(OUTPUT_DIR, f"raw_{timestamp}.jpg")
            final_path = os.path.join(OUTPUT_DIR, f"snapshot_{timestamp}.jpg")
            
            logger.info(f"🔄 Cycle started at {get_tehran_time()}")
            
            # 1. گرفتن اسکرین‌شات کامل
            if not take_screenshot(url, cookies, raw_path):
                continue
            
            # 2. برش تصویر (اگر فعال باشد)
            if CROP_ENABLED:
                if not crop_image(raw_path, final_path):
                    logger.warning("⚠️ Crop failed, using raw image")
                    final_path = raw_path
                else:
                    # حذف فایل خام اگر برش موفق بود
                    if Path(raw_path).exists() and raw_path != final_path:
                        Path(raw_path).unlink()
            else:
                final_path = raw_path
            
            # 3. ارسال به تلگرام
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            sent, last_sent_hash = loop.run_until_complete(
                send_telegram(bot_token, chat_id, final_path, last_sent_hash)
            )
            
            # 4. پاک‌سازی فایل‌های قدیمی
            cleanup_old_screenshots(OUTPUT_DIR, keep=10)
            
            # 5. محاسبه زمان خواب
            elapsed = time.time() - start
            sleep_time = max(0, INTERVAL_SECONDS - elapsed)
            if sleep_time > 0:
                logger.info(f"😴 Sleeping {sleep_time:.0f}s...")
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("👋 Interrupted, exiting...")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()

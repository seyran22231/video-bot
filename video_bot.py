"""
🎬 Видео-загрузчик Телеграм Бот
Скачивает видео с YouTube, TikTok, Instagram, VK и 1000+ сайтов

Установка:
  pip install python-telegram-bot yt-dlp

Запуск:
  python video_bot.py
"""

import os
import logging
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp

# ─── Настройки ────────────────────────────────────────────────
BOT_TOKEN = "8671241396:AAG1KwV0fnyAm9PNmCmXdJUfBB0Ixf3CqVg"  # Получи у @BotFather
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE_MB = 50  # Телеграм лимит для ботов без Nitro — 50 МБ

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── Вспомогательные функции ──────────────────────────────────

def get_video_info(url: str) -> dict | None:
    """Получаем информацию о видео без скачивания"""
    opts = {"quiet": True, "no_warnings": True, "extract_flat": False}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Ошибка получения инфо: {e}")
        return None


def download_video(url: str, quality: str, output_path: Path) -> tuple[bool, str]:
    """Скачиваем видео с нужным качеством"""
    
    format_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
        "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]",
        "audio": "bestaudio[ext=m4a]/bestaudio",
    }

    ydl_opts = {
        "format": format_map.get(quality, format_map["best"]),
        "outtmpl": str(output_path / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessors": [],
    }

    # Для аудио — конвертируем в mp3
    if quality == "audio":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if quality == "audio":
                filename = filename.rsplit(".", 1)[0] + ".mp3"
            return True, filename
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        return False, str(e)


# ─── Обработчики команд ───────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 *Привет! Я скачиваю видео.*\n\n"
        "Просто отправь мне ссылку на видео с:\n"
        "• YouTube\n"
        "• TikTok\n"
        "• Instagram\n"
        "• VK\n"
        "• Twitter/X\n"
        "• и 1000+ других сайтов\n\n"
        "⬇️ Скину видео прямо сюда в чат!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Как пользоваться:*\n\n"
        "1. Скопируй ссылку на видео\n"
        "2. Вставь её в этот чат\n"
        "3. Выбери качество\n"
        "4. Жди — бот скачает и пришлёт файл\n\n"
        "⚠️ *Ограничения:*\n"
        f"• Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ\n"
        "• Длинные видео могут не влезть\n\n"
        "❓ Если что-то не работает — попробуй другое качество"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем ссылку — показываем кнопки выбора качества"""
    url = update.message.text.strip()
    
    # Простая проверка что это URL
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ Это не похоже на ссылку. Отправь URL начинающийся с http:// или https://")
        return

    msg = await update.message.reply_text("🔍 Проверяю ссылку...")

    info = get_video_info(url)
    if not info:
        await msg.edit_text("❌ Не могу получить видео по этой ссылке.\n\nВозможно:\n• Видео приватное\n• Сайт не поддерживается\n• Неверная ссылка")
        return

    title = info.get("title", "Видео")[:50]
    duration = info.get("duration", 0)
    duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "неизвестно"

    # Сохраняем URL в контексте для последующего скачивания
    context.user_data["pending_url"] = url
    context.user_data["pending_title"] = title

    keyboard = [
        [
            InlineKeyboardButton("🎬 Лучшее качество", callback_data="q_best"),
            InlineKeyboardButton("📺 720p", callback_data="q_720p"),
        ],
        [
            InlineKeyboardButton("📱 480p", callback_data="q_480p"),
            InlineKeyboardButton("📟 360p", callback_data="q_360p"),
        ],
        [InlineKeyboardButton("🎵 Только аудио (MP3)", callback_data="q_audio")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(
        f"✅ *Найдено:*\n{title}\n⏱ Длительность: {duration_str}\n\n*Выбери качество:*",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def handle_quality_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Юзер выбрал качество — скачиваем"""
    query = update.callback_query
    await query.answer()

    quality_map = {
        "q_best": ("best", "лучшее качество"),
        "q_720p": ("720p", "720p"),
        "q_480p": ("480p", "480p"),
        "q_360p": ("360p", "360p"),
        "q_audio": ("audio", "аудио MP3"),
    }

    quality_key, quality_label = quality_map.get(query.data, ("best", "лучшее"))
    url = context.user_data.get("pending_url")
    title = context.user_data.get("pending_title", "Видео")

    if not url:
        await query.edit_message_text("❌ Сессия устарела. Отправь ссылку заново.")
        return

    await query.edit_message_text(f"⏳ Скачиваю *{title}*\nКачество: {quality_label}\n\nЭто может занять минуту...", parse_mode="Markdown")

    # Папка для этого пользователя
    user_dir = DOWNLOAD_DIR / str(query.from_user.id)
    user_dir.mkdir(exist_ok=True)

    # Скачиваем в отдельном потоке чтобы не блокировать бота
    loop = asyncio.get_event_loop()
    success, result = await loop.run_in_executor(
        None, download_video, url, quality_key, user_dir
    )

    if not success:
        await query.edit_message_text(
            f"❌ Не удалось скачать.\n\nПричина: {result}\n\nПопробуй другое качество или другую ссылку."
        )
        return

    file_path = Path(result)
    if not file_path.exists():
        # yt-dlp иногда меняет расширение — ищем файл
        files = list(user_dir.glob("*"))
        if files:
            file_path = max(files, key=lambda f: f.stat().st_mtime)
        else:
            await query.edit_message_text("❌ Файл не найден после скачивания.")
            return

    file_size_mb = file_path.stat().st_size / (1024 * 1024)

    if file_size_mb > MAX_FILE_SIZE_MB:
        file_path.unlink(missing_ok=True)
        await query.edit_message_text(
            f"❌ Файл слишком большой ({file_size_mb:.1f} МБ).\n"
            f"Телеграм разрешает максимум {MAX_FILE_SIZE_MB} МБ.\n\n"
            "Попробуй меньшее качество (480p или 360p)."
        )
        return

    await query.edit_message_text("📤 Загружаю в Телеграм...")

    try:
        with open(file_path, "rb") as f:
            if quality_key == "audio":
                await query.message.reply_audio(
                    audio=f,
                    title=title,
                    caption="🎵 Готово!",
                )
            else:
                await query.message.reply_video(
                    video=f,
                    caption=f"🎬 {title}\n\n_Скачано ботом_",
                    parse_mode="Markdown",
                    supports_streaming=True,
                )
        await query.edit_message_text("✅ Готово!")
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await query.edit_message_text(f"❌ Не удалось отправить файл: {e}")
    finally:
        # Удаляем файл после отправки
        file_path.unlink(missing_ok=True)


# ─── Запуск ───────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_quality_choice, pattern="^q_"))

    print("🤖 Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

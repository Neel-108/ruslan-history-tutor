"""
main_ruslan.py
Entry point for RUSLAN History Tutor Bot
Initializes database, registers handlers, and starts polling
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from config_ruslan import TELEGRAM_BOT_TOKEN
from ruslan_database_v3_4 import init_db
from bot_ruslan_2 import router

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# BOT COMMANDS MENU
# ============================================================================

async def setup_bot_commands(bot: Bot):
    """
    Set up bot menu commands visible in Telegram interface
    
    These appear in the menu when user types "/" in chat
    """
    commands = [
        BotCommand(command="start", description="Начать / Выбрать класс"),
        BotCommand(command="stats", description="Статистика токенов"),
        BotCommand(command="report", description="Отчёт за 7 дней"),
        BotCommand(command="reset", description="Сбросить профиль")
    ]
    await bot.set_my_commands(commands)
    logger.info("Bot commands menu set up")

# ============================================================================
# MAIN FUNCTION
# ============================================================================

async def main():
    """
    Main entry point
    
    Flow:
    1. Initialize database (create tables if needed)
    2. Create bot and dispatcher instances
    3. Register handlers from bot_ruslan_fixed module
    4. Set up bot commands menu
    5. Start polling for messages
    """
    
    # ========================================================================
    # STEP 1: Initialize database
    # ========================================================================
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")
    
    # ========================================================================
    # STEP 2: Create bot and dispatcher
    # ========================================================================
    logger.info("Creating bot instance...")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    
    # ========================================================================
    # STEP 3: Register handlers
    # ========================================================================
    logger.info("Registering handlers...")
    dp.include_router(router)
    logger.info("Handlers registered")
    
    # ========================================================================
    # STEP 4: Setup bot commands menu
    # ========================================================================
    await setup_bot_commands(bot)
    
    # ========================================================================
    # STEP 5: Start polling
    # ========================================================================
    logger.info("=" * 60)
    logger.info("🚀 RUSLAN History Tutor Bot started successfully!")
    logger.info("=" * 60)
    
    try:
        # Start polling (runs indefinitely until stopped)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Cleanup on shutdown
        await bot.session.close()
        logger.info("Bot stopped")

# ============================================================================
# RUN BOT
# ============================================================================

if __name__ == "__main__":
    """
    Entry point when running: python main_ruslan.py
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
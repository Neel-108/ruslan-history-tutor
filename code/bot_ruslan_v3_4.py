"""
bot_ruslan.py
Main bot handlers for RUSLAN History Tutor Bot
Fixed: Issues 4, 5, 7 (topic resolution, abuse accounting, WARM lifecycle)
"""

import logging
import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config_ruslan import (
    ADMIN_TELEGRAM_ID,
    ALLOWED_USERS,
    BETA_MESSAGE,
    GIBBERISHRESPONSE,
    ABUSE_WORDS,
    ABUSE_PENALTY_TOKENS,
    DISCLAIMER,
    INITIAL_TOKEN_GRANT,
    CASUAL_RESPONSES,  # NEW
    ABUSE_RESPONSES,  # NEW
    MAX_TOKENS_BY_GRADE,
    LITE_TOKEN_RATIO
)


import ruslan_database_v3_4 as database
from ruslan_classifier_v3_4 import classify_intent
from ruslan_prompt_builder_v3_4 import build_prompt, extract_checkpoint_simple, MODE
from ruslan_logic_v3_4 import RuslanLogic
from ruslan_session_mgr_v3_4 import SessionManager
from ruslan_yandex_api_pro import call_yandex_gpt_pro
from topic_resolver_ruslan import get_topic_resolver

logger = logging.getLogger(__name__)
router = Router()

# Module-level singletons
ruslan_logic = RuslanLogic()
session_manager = SessionManager()
topic_resolver = get_topic_resolver()

# ============================================================================
# ACCESS CONTROL HELPERS
# ============================================================================
    
async def is_whitelisted(telegram_id: int) -> bool:
    """Check if user is whitelisted"""
    if telegram_id in ALLOWED_USERS:
        return True
    # Check database for dynamic whitelist
    user = await database.get_user(telegram_id)
    return user and user.get('ispaid', 0) == 1


def is_admin(telegram_id: int) -> bool:
    """Check if user is admin"""
    return telegram_id == ADMIN_TELEGRAM_ID

# ============================================================================
# ACCOUNTING LAYER (Issue 5 fix)
# ============================================================================

async def apply_abuse_penalty(user_id: int, intent: str):
    """
    Centralized abuse penalty accounting
    
    Args:
        user_id: User's Telegram ID
        intent: Classified intent label
    """
    await database.deduct_tokens(user_id, ABUSE_PENALTY_TOKENS)
    await database.log_usage(user_id, ABUSE_PENALTY_TOKENS, 'penalty', intent, 'ABUSE_PENALTY', None)
    logger.warning(f"User {user_id} penalized {ABUSE_PENALTY_TOKENS} tokens for abuse")

# ============================================================================
# WARM SUMMARY GENERATION (Issue 7 fix)
# ============================================================================

    
async def maybe_update_warm_summary(user_id: int, topic: str, checkpoint: str):
    """
    Update WARM summary after teaching session
    
    Args:
        user_id: User's Telegram ID
        topic: Current canonical topic
        checkpoint: Latest checkpoint reached
    """
    if not checkpoint:
        return
    
    topic_label = topic if topic else "текущая тема"
    
    # Get existing summary
    existing_summary = await database.get_warm_summary(user_id) or ""
    
    # Simple append logic (MVP)
    if existing_summary:
        new_summary = f"{existing_summary}; {topic_label}: {checkpoint}"
    else:
        new_summary = f"{topic_label}: {checkpoint}"
    
    # Truncate if too long (keep last 500 chars)
    if len(new_summary) > 500:
        new_summary = "..." + new_summary[-497:]
    
    await database.update_warm_summary(user_id, new_summary)
    logger.info(f"User {user_id} WARM summary updated")


# ============================================================================
# /start COMMAND - Grade selection
# ============================================================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command - show grade selection"""
    user_id = message.from_user.id
    
    if not await is_whitelisted(user_id):
        await message.answer(BETA_MESSAGE)
        return
    
    user = await database.get_user(user_id)
    if not user:
        await database.create_user(user_id)
        logger.info(f"New user registered: {user_id}")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 класс", callback_data="grade_5"),
         InlineKeyboardButton(text="6 класс", callback_data="grade_6"),
         InlineKeyboardButton(text="7 класс", callback_data="grade_7")],
        [InlineKeyboardButton(text="8 класс", callback_data="grade_8"),
         InlineKeyboardButton(text="9 класс", callback_data="grade_9"),
         InlineKeyboardButton(text="10 класс", callback_data="grade_10")],
        [InlineKeyboardButton(text="11 класс", callback_data="grade_11")]
    ])
    
    await message.answer(
        "Привет! Я твой репетитор по истории России.\n\n"
        "Выбери свой класс:",
        reply_markup=keyboard
    )

@router.callback_query(lambda c: c.data.startswith("grade_"))
async def process_grade_selection(callback: CallbackQuery):
    """Handle grade button click"""
    user_id = callback.from_user.id
    grade = int(callback.data.split("_")[1])
    
    await database.update_user_grade(user_id, grade)
    await database.update_user_textbook(user_id, "FGOS Standard")
    session_manager.clear_session(user_id)  # NEW: Clear session on grade change
    logger.info(f"User {user_id} selected grade {grade}")
    
    await callback.message.edit_text(
        f"✓ Класс {grade} выбран!\n"
        #f"Учебник: FGOS Standard\n\n"
        "Теперь можешь задавать вопросы по истории России.\n"
        "Используй /help для справки."
    )
    await callback.answer()


# ============================================================================
# /help COMMAND
# ============================================================================

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show help information"""
    help_text = """📚 **Как использовать бота:**

**Настройки:**
• /start - Выберите класс

**Обучение:**
• Задавайте вопросы по истории России для вашего класса
• Бот следует учебной программе Федерального государственного образовательного стандарта (ФГЭС) для вашего класса
• Бот НЕ выполняет домашние задания, но помогает вам разобраться

**Команды:**
• /stats - Баланс коины
• /report - Отчет за 7 дней
• /reset - Сбросить профиль
• /help - Эта справка

**О коины:**
• Каждый вопрос расходует коины
• Когда у бота останется 0 монет, он остановится."""
    
    await message.answer(help_text)

# ============================================================================
# /stats COMMAND
# ============================================================================

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Show token usage statistics"""
    user_id = message.from_user.id
    
    if not await is_whitelisted(user_id):
        await message.answer(BETA_MESSAGE)
        return
    
    user = await database.get_user(user_id)
    if not user:
        await message.answer("Используй /start для регистрации.")
        return
    
    balance = user['tokens']
    consumed = INITIAL_TOKEN_GRANT - balance
    
    await message.answer(
        f"📊 Статистика использования:\n\n"
        f"💰 Баланс токенов: {balance:,}\n"
        f"📈 Использовано: {consumed:,} / {INITIAL_TOKEN_GRANT:,}\n\n"
        f"Сегодня:\n"
        f"└─ Сообщений: {user['messagecount']}"
    )


# ============================================================================
# /report COMMAND
# ============================================================================


@router.message(Command("report"))
async def cmd_report(message: Message):
    """
    Handle /report command
    Show detailed 7-day usage breakdown for parental monitoring
    """
    user_id = message.from_user.id
    
    # Check whitelist
    if not await is_whitelisted(user_id):
        await message.answer(BETA_MESSAGE)
        return
    
    # Get 7-day report from audit log
    report = await database.get_usage_report(user_id, days=7)
    
    if report['total_messages'] == 0:
        await message.answer("📊 Отчёт пуст. Нет активности за последние 7 дней.")
        return
    
    # Build report message
    report_text = f"📊 Отчёт за последние 7 дней:\n\n"
    report_text += f"Всего:\n"
    report_text += f"├─ Сообщений: {report['total_messages']}\n"
    report_text += f"├─ Обучающих: {report['total_teaching']}\n"
    report_text += f"├─ Casual чатов: {report['total_casual']}\n"
    
    report_text += f"└─ Токенов: {report['total_tokens']:,}\n\n"
    
    # Add daily breakdown
    if report['daily_breakdown']:
        report_text += "По дням:\n"
        for day in report['daily_breakdown'][:7]:  # Last 7 days
            date = day['date']
            tokens = day['tokens'] or 0
            teaching = day['teaching_count'] or 0
            casual = day['casual_count'] or 0
            abuse = day['abuse_count'] or 0
            
            report_text += f"\n{date}:\n"
            report_text += f"  ├─ Обучающих: {teaching}\n"
            report_text += f"  ├─ Casual: {casual}\n"
           
            report_text += f"  └─ Токенов: {tokens:,}\n"
    
    # Calculate cost
    cost_total = (report['total_tokens'] / 1000) * 0.40
    
    await message.answer(report_text)

# ============================================================================
# /reset COMMAND
# ============================================================================

@router.message(Command("reset"))
async def cmd_reset(message: Message):
    """Reset user profile"""
    user_id = message.from_user.id
    
    if not await is_whitelisted(user_id):
        await message.answer(BETA_MESSAGE)
        return
    
    await database.reset_user_progress(user_id)
    session_manager.clear_session(user_id)
    
    await message.answer(
        "✓ Профиль сброшен.\n\n"
        "Используй /start для новой настройки.\n\n"
    )
    logger.info(f"User {user_id} reset profile")

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

@router.message(Command("grant"))
async def cmd_grant(message: Message):
    """Admin: grant tokens to user"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Формат: /grant telegram_id tokens")
            return
        
        target_id = int(parts[1])
        tokens = int(parts[2])
        
        await database.grant_tokens(target_id, tokens)
        await message.answer(f"✓ Добавлено {tokens:,} токенов пользователю {target_id}")
        logger.info(f"Admin {message.from_user.id} granted {tokens} tokens to {target_id}")
        
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        
        
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """Admin: Broadcast message to all users"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        broadcast_text = message.text.replace("/broadcast", "").strip()
        if not broadcast_text:
            await message.answer("Использование: /broadcast <текст сообщения>")
            return
        
        users = await database.get_all_users()
        sent_count = 0
        
        for telegram_id in users:
            try:
                await message.bot.send_message(telegram_id, broadcast_text)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {telegram_id}: {e}")
        
        await message.answer(f"✅ Сообщение отправлено {sent_count} пользователям")
        logger.info(f"Admin {message.from_user.id} broadcast to {sent_count} users")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

@router.message(Command("adminstats"))
async def cmd_admin_stats(message: Message):
    """Admin: View system statistics"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        stats = await database.get_user_stats_summary()
        
        stats_text = "📊 **Статистика системы**\n\n"
        stats_text += f"👥 Пользователей: {stats['total_users']}\n"
        stats_text += f"🔥 Токенов использовано: {stats['total_tokens_consumed']:,}\n"
        stats_text += f"💰 Токенов осталось: {stats['total_tokens_remaining']:,}\n"
        stats_text += f"📈 Среднее сообщений сегодня: {stats['avg_messages_today']}"
        
        await message.answer(stats_text)
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")
        
@router.message(Command("admincost"))
async def cmd_admin_cost(message: Message):
    """Admin: Calculate specific user's total cost"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /admincost <telegram_id>")
            return
        
        target_id = int(args[1])
        
        # Get usage from logs
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT SUM(tokens_used) as total, model_used FROM usage_log WHERE telegram_id = ? GROUP BY model_used",
                (target_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        
        pro_tokens = 0
        lite_tokens = 0
        
        for row in rows:
            if row[1] == 'pro':
                pro_tokens = row[0] or 0
            elif row[1] == 'lite':
                lite_tokens = row[0] or 0
        
        pro_cost = pro_tokens / 1000 * 0.61
        lite_cost = lite_tokens / 1000 * 0.10
        total_cost = pro_cost + lite_cost
        
        cost_text = f"💰 **Расходы пользователя {target_id}**\n\n"
        cost_text += f"🔵 Pro: {pro_tokens:,} токенов = {pro_cost:.2f} ₽\n"
        cost_text += f"🟢 Lite: {lite_tokens:,} токенов = {lite_cost:.2f} ₽\n"
        cost_text += f"📊 Всего: {total_cost:.2f} ₽"
        
        await message.answer(cost_text)
        
    except ValueError:
        await message.answer("Ошибка: укажите корректный telegram_id")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Использование: /whitelist telegram_id")
            return
        target_id = int(parts[1])
        await database.set_paid_status(target_id, True)
        await message.answer(f"✅ {target_id} добавлен")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("unwhitelist"))
async def cmd_unwhitelist(message: Message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Использование: /unwhitelist telegram_id")
            return
        target_id = int(parts[1])
        await database.set_paid_status(target_id, False)
        await message.answer(f"❌ {target_id} удалён")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")



# ============================================================================
# MAIN MESSAGE HANDLER
# ============================================================================

@router.message(F.text)
async def handle_message(message: Message):
    """
    Main message handler - complete flow
    
    FIXED:
    - Issue 4: Canonical topic resolution
    - Issue 5: Centralized abuse accounting
    - Issue 7: WARM summary lifecycle
    """
    
    user_id = message.from_user.id
    user_message = message.text.strip()
    
    # ========================================================================
    # TIER-0: HARD CHECKS (No LLM)
    # ========================================================================
    
    if not await is_whitelisted(user_id):
        await message.answer(BETA_MESSAGE)
        return
    
    user = await database.get_user(user_id)
    
    if not user:
        await database.create_user(user_id)
        await message.answer("Используй /start для настройки профиля.")
        return
    
    if not user['grade']:
        await message.answer("Используй /start для выбора класса.")
        return
    
    balance = user['tokens']
    if balance <= 0:
        await message.answer(
            "❌ У тебя закончились токены.\n\n"
            "Свяжись с администратором для пополнения.\n\n"
        )
        return
    
    # After balance check, line ~271
    cleaned = user_message.strip()
    
    is_gibberish = (
        len(cleaned) < 3 or 
        not any(c.isalpha() for c in cleaned) or
        len(set(cleaned)) / len(cleaned) < 0.4 or  # Raise to 40%
        any(c.isdigit() for c in cleaned) and len(cleaned) < 20  # Any digits in short text
    )


    if is_gibberish:
        await message.answer(GIBBERISHRESPONSE)
        #await database.log_usage(user_id, 0, None, "CASUAL", "GIBBERISH_FILTER", None)
        await database.log_usage(user_id, 0, None, "GIBBERISH", "GIBBERISH_FILTER", None)
        return
        
    # Hard-coded greeting filter (before Lite)
    casual_keywords = ['привет', 'здравствуйте', 'доброе утро', 'добрый день', 'добрый вечер', 'hi', 'hello', 'good morning', 'good afternoon', 'good evening', 'пока', 'до свидания', 'bye', 'goodbye']
    if any(keyword in user_message.lower() for keyword in casual_keywords):
        import random
        await message.answer(random.choice(CASUAL_RESPONSES))
        return


    # FGOS validation
    is_valid, refusal_msg = ruslan_logic.validate_question(user_message, user['grade'])
    if not is_valid:
        await message.answer(refusal_msg)
        return
    
    # ========================================================================
    # TIER-1: LITE CLASSIFICATION
    # ========================================================================
    
    # Get last bot response for context-aware classification
    all_turns = session_manager.get_recent_turns(user_id, n_turns=1)
    last_bot_response = all_turns[0] if all_turns else None

    intent, lite_tokens = await classify_intent(user_message, last_response=last_bot_response, timeout=10.0)
    logger.info(f"User {user_id} classified as: {intent}, lite tokens: {lite_tokens}")
    
    # ========================================================================
    # ABUSE DETECTION (Backend) - Issue 5 fix
    # ========================================================================
    
    is_abuse = any(word in user_message.lower() for word in ABUSE_WORDS)
    
    if is_abuse:
        await apply_abuse_penalty(user_id, intent)
    
    # ========================================================================
    # HANDLE CASUAL
    # ========================================================================
        
    if intent == "CASUAL":
        import random
        await message.answer(random.choice(CASUAL_RESPONSES))
        #await database.log_usage(user_id, 0, None, 'CASUAL', 'TEMPLATE', None)
        
        # Deduct Lite tokens only
        lite_equivalent = int(int(lite_tokens) * LITE_TOKEN_RATIO)
        await database.deduct_tokens(user_id, lite_equivalent)
        await database.log_usage(user_id, lite_tokens, 'lite', 'CASUAL', 'TEMPLATE', None)
        return

    
    # ========================================================================
    # HANDLE PURE ABUSE
    # ========================================================================
        
    if intent == "ABUSE":
        import random
        await message.answer(random.choice(ABUSE_RESPONSES))
       # await database.log_usage(user_id, 0, None, 'ABUSE', 'TEMPLATE', None)
       
        # Deduct Lite tokens only (penalty already applied)
        lite_equivalent = int(int(lite_tokens) * LITE_TOKEN_RATIO)
        await database.deduct_tokens(user_id, lite_equivalent)
        await database.log_usage(user_id, lite_tokens, 'lite', 'ABUSE', 'TEMPLATE', None)
        return
    
    # ========================================================================
    # ISSUE 4 FIX: CANONICAL TOPIC RESOLUTION
    # ========================================================================
    
    canonical_topic, topic_valid, topic_refusal_msg = topic_resolver.resolve_topic(
        user_message, 
        user['grade']
    )
    
    if not topic_valid:
        # Grade mismatch - refuse
        await message.answer(topic_refusal_msg)
        return
    
    # ========================================================================
    # BACKEND MODE DECISION
    # ========================================================================
        
    hot_state = await database.get_hot_state(user_id)

    # Check if recent conversation exists for CONTINUE
    all_turns = session_manager.get_recent_turns(user_id, n_turns=1)
    has_recent_conversation = len(all_turns) > 0

    if intent == "CONTINUE" and has_recent_conversation:
        mode = MODE.CONTINUE
    elif intent == "REVISION":
        mode = MODE.REVISION
    elif intent == "MIXED":
        mode = MODE.TEACH
    else:
        mode = MODE.TEACH
   
    logger.info(f"User {user_id} mode: {mode.value}, topic: {canonical_topic}")
    
    # ========================================================================
    # TEACHING FLOW (TIER-2)
    # ========================================================================
    
    try:
        context_turns = session_manager.get_recent_turns(user_id, n_turns=3)
        
        warm_summary = ""
        if mode == MODE.REVISION:
            warm_summary = await database.get_warm_summary(user_id) or ""
        
        full_prompt = build_prompt(
            db_state=hot_state,
            user_input=user_message,
            context_turns=context_turns,
            warm_summary=warm_summary,
            mode=mode
        )

        
        max_tokens = MAX_TOKENS_BY_GRADE.get(user['grade'], 500)
        
        logger.info(f"Calling Pro for user {user_id}, mode: {mode.value}")
        result = await call_yandex_gpt_pro(full_prompt, max_tokens)
        
        answer = result['answer']
        tokens_used = result['tokens']['total']
        
        # Extract checkpoint
        checkpoint = None
        if mode in [MODE.TEACH, MODE.CONTINUE]:
            checkpoint = extract_checkpoint_simple(answer)
            if checkpoint:
                await database.update_hot_state(
                    user_id,
                    current_checkpoint=checkpoint,
                    mode=mode.value
                )
        
        # ISSUE 4 FIX: Use canonical topic (not user text)
        if mode == MODE.TEACH and canonical_topic:
            await database.update_hot_state(
                user_id,
                current_topic=canonical_topic,
                mode=mode.value
            )
        
        # ISSUE 7 FIX: Update WARM summary

        if mode in (MODE.TEACH, MODE.CONTINUE) and checkpoint:    
            await maybe_update_warm_summary(user_id, canonical_topic, checkpoint)
        
        final_response = answer + DISCLAIMER
        
        checkpoint_for_session = checkpoint if checkpoint else answer[:200]
        session_manager.add_message(user_id, user_message, checkpoint_for_session)

        # Calculate combined token deduction
        lite_equivalent = int(int(lite_tokens) * LITE_TOKEN_RATIO)
        total_to_deduct = tokens_used + lite_equivalent

        await database.deduct_tokens(user_id, total_to_deduct)

        await database.log_usage(user_id, tokens_used, 'pro', intent, mode.value, canonical_topic or hot_state.get('current_topic'))
        await database.log_usage(user_id, lite_tokens, 'lite', 'CLASSIFIER', mode.value, None)

        await database.increment_message_count(user_id)
        await message.answer(final_response)

        logger.info(f"User {user_id} response sent, tokens: {total_to_deduct} (Pro: {tokens_used} + Lite: {lite_equivalent}), mode: {mode.value}")

        
    except Exception as e:
        logger.error(f"Error processing message for user {user_id}: {e}")
        await message.answer(
            "Произошла ошибка при обработке запроса.\n\n"
            "Попробуй ещё раз или обратись в поддержку.\n\n"
        )
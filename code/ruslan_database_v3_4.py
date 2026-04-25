# database.py
# RUSLAN v3.4 database layer
# HOT STATE (always injected) + WARM summary (conditional) + COLD log

import aiosqlite
import json
from datetime import datetime, timedelta

DB_PATH = "ruslan.db"

# ============================================================================
# INITIALIZATION
# ============================================================================

async def init_db():
    """Initialize SQLite database with v3.4 schema"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                userid INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                tokens INTEGER DEFAULT 200000,
                messagecount INTEGER DEFAULT 0,
                ispaid BOOLEAN DEFAULT 0,
                createdat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- HOT STATE (Layer A)
                grade INTEGER DEFAULT 7,
                textbook TEXT DEFAULT 'FGOS Standard',
                current_topic TEXT DEFAULT NULL,
                current_checkpoint TEXT DEFAULT NULL,
                mode TEXT DEFAULT NULL,
                
                -- WARM SUMMARY (Layer B)
                warm_summary TEXT DEFAULT NULL,
                
                -- Legacy (keep for backward compatibility)
                completed_topics TEXT DEFAULT '[]'
            )
        """)
        
        # COLD LOG (Layer C) - usage tracking
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tokens_used INTEGER NOT NULL,
                model_used TEXT,
                intent_label TEXT,
                mode TEXT,
                topic_studied TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            )
        """)
        
        await db.commit()

# ============================================================================
# USER MANAGEMENT
# ============================================================================

async def get_user(telegram_id: int):
    """
    Get user by Telegram ID.
    
    Returns:
        User row as dict or None if not found
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(telegram_id: int):
    """Create new user with initial 200K tokens"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (telegram_id, tokens, messagecount, ispaid, completed_topics) VALUES (?, 200000, 0, 0, '[]')",
            (telegram_id,)
        )
        await db.commit()

# ============================================================================
# TOKEN & MESSAGE LIMITS
# ============================================================================

async def get_user_tokens(telegram_id: int) -> int:
    """Get user's token balance"""
    user = await get_user(telegram_id)
    return user['tokens'] if user else None

async def update_user_tokens(telegram_id: int, new_balance: int):
    """Update user's token balance"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET tokens = ? WHERE telegram_id = ?",
            (new_balance, telegram_id)
        )
        await db.commit()

# ADD these 2 functions to database_v3_4.py (after update_user_tokens function)

async def deduct_tokens(telegram_id: int, tokens: int):
    """
    Deduct tokens from user balance (convenience wrapper)
    
    Args:
        telegram_id: User's Telegram ID
        tokens: Number of tokens to deduct
    """
    balance = await get_user_tokens(telegram_id)
    new_balance = max(0, balance - tokens)  # Don't go negative
    await update_user_tokens(telegram_id, new_balance)


async def grant_tokens(telegram_id: int, tokens: int):
    """
    Grant tokens to user (admin function)
    
    Args:
        telegram_id: User's Telegram ID
        tokens: Number of tokens to grant
    """
    balance = await get_user_tokens(telegram_id)
    new_balance = balance + tokens
    await update_user_tokens(telegram_id, new_balance)


async def update_user_grade(telegram_id: int, grade: int):
    """Update user's grade"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET grade = ? WHERE telegram_id = ?", (grade, telegram_id)
        )
        await db.commit()


async def update_user_textbook(telegram_id: int, textbook: str):
    """Update user's textbook"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET textbook = ? WHERE telegram_id = ?", (textbook, telegram_id)
        )
        await db.commit()

async def get_message_count(telegram_id: int) -> int:
    """Get user's daily message count"""
    user = await get_user(telegram_id)
    return user['messagecount'] if user else 0

async def increment_message_count(telegram_id: int):
    """Increment user's daily message counter"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET messagecount = messagecount + 1 WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

async def reset_daily_counters():
    """Reset all users' message counts (run at midnight UTC via cron)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messagecount = 0")
        await db.execute("UPDATE users SET last_reset = CURRENT_TIMESTAMP")
        await db.commit()

async def set_paid_status(telegram_id: int, is_paid: bool):
    """Update user's paid subscription status"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET ispaid = ? WHERE telegram_id = ?",
            (1 if is_paid else 0, telegram_id)
        )
        await db.commit()

# ============================================================================
# LAYER A: HOT STATE (Always injected)
# ============================================================================

async def get_hot_state(telegram_id: int) -> dict:
    """
    Get HOT STATE for user.
    Always injected into Pro call.
    
    Returns:
        Dict with: grade, textbook, current_topic, current_checkpoint, mode
    """
    user = await get_user(telegram_id)
    if not user:
        return {
            'grade': 7,
            'textbook': 'FGOS Standard',
            'current_topic': None,
            'current_checkpoint': None,
            'mode': None
        }
    
    return {
        'grade': user['grade'],
        'textbook': user.get('textbook', 'FGOS Standard'),
        'current_topic': user.get('current_topic'),
        'current_checkpoint': user.get('current_checkpoint'),
        'mode': user.get('mode')
    }

async def update_hot_state(
    telegram_id: int,
    grade: int = None,
    textbook: str = None,
    current_topic: str = None,
    current_checkpoint: str = None,
    mode: str = None
):
    """
    Update HOT STATE fields.
    Only updates fields that are provided (not None).
    """
    user = await get_user(telegram_id)
    if not user:
        return
    
    updates = []
    values = []
    
    if grade is not None:
        updates.append("grade = ?")
        values.append(grade)
    if textbook is not None:
        updates.append("textbook = ?")
        values.append(textbook)
    if current_topic is not None:
        updates.append("current_topic = ?")
        values.append(current_topic)
    if current_checkpoint is not None:
        updates.append("current_checkpoint = ?")
        values.append(current_checkpoint)
    if mode is not None:
        updates.append("mode = ?")
        values.append(mode)
    
    if not updates:
        return
    
    values.append(telegram_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?",
            tuple(values)
        )
        await db.commit()

async def clear_hot_state(telegram_id: int):
    """Clear HOT STATE (reset to None)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET current_topic = NULL, current_checkpoint = NULL, mode = NULL WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

# ============================================================================
# LAYER B: WARM SUMMARY (Conditionally injected)
# ============================================================================

async def get_warm_summary(telegram_id: int) -> str | None:
    """
    Get WARM summary for user.
    Injected ONLY when backend decides (revision, backward jump, conflict).
    
    Returns:
        WARM summary string or None
    """
    user = await get_user(telegram_id)
    if not user:
        return None
    
    return user.get('warm_summary')

async def update_warm_summary(telegram_id: int, summary: str):
    """
    Update WARM summary (overwrite, not append).
    Called on lesson boundaries by backend.
    
    CRITICAL: WARM summary is OVERWRITTEN each lesson boundary.
    No appending. No merging. Hard size cap enforced by caller.
    
    Args:
        telegram_id: User ID
        summary: Bullet-style factual recap (size-capped by backend)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET warm_summary = ? WHERE telegram_id = ?",
            (summary, telegram_id)
        )
        await db.commit()

async def clear_warm_summary(telegram_id: int):
    """Clear WARM summary"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET warm_summary = NULL WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

# ============================================================================
# LAYER C: COLD LOG (Never injected, audit only)
# ============================================================================

async def log_usage(
    telegram_id: int,
    tokens_used: int,
    model_used: str = None,
    intent_label: str = None,
    mode: str = None,
    topic_studied: str = None
):
    """
    Log usage to COLD log.
    Never injected into prompts.
    
    Args:
        telegram_id: User's Telegram ID
        tokens_used: Number of tokens consumed
        model_used: "lite" or "pro"
        intent_label: CASUAL, ABUSE, TEACH, etc.
        mode: TEACH, CONTINUE, REVISION, REFUSE
        topic_studied: Topic name if applicable
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO usage_log 
               (telegram_id, tokens_used, model_used, intent_label, mode, topic_studied) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, tokens_used, model_used, intent_label, mode, topic_studied)
        )
        await db.commit()

# async def get_usage_report(telegram_id: int, days: int = 7):
    # """
    # Get usage report from COLD log.
    
    # Returns dict with:
        # - daily_breakdown: list of daily stats
        # - total_tokens: sum of all tokens
        # - total_messages: count of all messages
    # """
    # async with aiosqlite.connect(DB_PATH) as db:
        # db.row_factory = aiosqlite.Row
        
        # start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # async with db.execute(
            # """SELECT 
                # DATE(timestamp) as date,
                # SUM(tokens_used) as tokens,
                # COUNT(*) as messages,
                # SUM(CASE WHEN model_used = 'lite' THEN 1 ELSE 0 END) as lite_calls,
                # SUM(CASE WHEN model_used = 'pro' THEN 1 ELSE 0 END) as pro_calls,
                # GROUP_CONCAT(DISTINCT topic_studied) as topics
            # FROM usage_log 
            # WHERE telegram_id = ? AND DATE(timestamp) >= ?
            # GROUP BY DATE(timestamp)
            # ORDER BY DATE(timestamp) DESC""",
            # (telegram_id, start_date)
        # ) as cursor:
            # rows = await cursor.fetchall()
            
            # daily_breakdown = []
            # total_tokens = 0
            # total_messages = 0
            
            # for row in rows:
                # row_dict = dict(row)
                # daily_breakdown.append(row_dict)
                # total_tokens += row_dict['tokens'] or 0
                # total_messages += row_dict['messages'] or 0
            
            # return {
                # 'daily_breakdown': daily_breakdown,
                # 'total_tokens': total_tokens,
                # 'total_messages': total_messages,
                # 'days': days
            # }
            
async def get_usage_report(telegram_id: int, days: int = 7):
    """
    Get usage report for last N days from audit log
    
    Args:
        telegram_id: User's Telegram ID
        days: Number of days to report (default 7)
        
    Returns:
        {
            'daily_breakdown': [...],
            'total_tokens': int,
            'total_messages': int,
            'total_teaching': int,
            'total_casual': int,
            'total_abuse_penalties': int,
            'days': int
        }
    """
    from datetime import datetime, timedelta
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Calculate start date
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Get daily breakdown
        # async with db.execute(
            # """SELECT 
                # DATE(timestamp) as date,
                # SUM(tokens_used) as tokens,
                # COUNT(*) as messages,
                # SUM(CASE WHEN query_type = 'teaching' THEN 1 ELSE 0 END) as teaching_count,
                # SUM(CASE WHEN query_type = 'casual' THEN 1 ELSE 0 END) as casual_count,
                # SUM(CASE WHEN query_type = 'abuse_penalty' THEN 1 ELSE 0 END) as abuse_count
            # FROM usage_log 
            # WHERE telegram_id = ? AND DATE(timestamp) >= ?
            # GROUP BY DATE(timestamp)
            # ORDER BY DATE(timestamp) DESC""",
            # (telegram_id, start_date)
        # ) as cursor:
            # rows = await cursor.fetchall()
            
        async with db.execute(
            """SELECT 
                DATE(timestamp) as date,
                SUM(tokens_used) as tokens,
                COUNT(*) as messages,
                SUM(CASE WHEN intent_label IN ('TEACH', 'CONTINUE', 'REVISION', 'MIXED') THEN 1 ELSE 0 END) as teaching_count,
                SUM(CASE WHEN intent_label = 'CASUAL' THEN 1 ELSE 0 END) as casual_count,
                SUM(CASE WHEN intent_label = 'GIBBERISH' THEN 1 ELSE 0 END) as gibberish_count,
                SUM(CASE WHEN intent_label = 'ABUSE' THEN 1 ELSE 0 END) as abuse_count
            FROM usage_log 
            WHERE telegram_id = ? AND DATE(timestamp) >= ?
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp) DESC""",
            (telegram_id, start_date)
        ) as cursor:
            rows = await cursor.fetchall()

            
            daily_breakdown = []
            total_tokens = 0
            total_messages = 0
            total_teaching = 0
            total_casual = 0
            total_abuse = 0
            
            for row in rows:
                row_dict = dict(row)
                daily_breakdown.append(row_dict)
                total_tokens += row_dict['tokens'] or 0
                total_messages += row_dict['messages'] or 0
                total_teaching += row_dict['teaching_count'] or 0
                total_casual += row_dict['casual_count'] or 0
                total_abuse += row_dict['abuse_count'] or 0
            
            return {
                'daily_breakdown': daily_breakdown,
                'total_tokens': total_tokens,
                'total_messages': total_messages,
                'total_teaching': total_teaching,
                'total_casual': total_casual,
                'total_abuse_penalties': total_abuse,
                'days': days
            }

# ============================================================================
# LEGACY / COMPATIBILITY (Keep for now)
# ============================================================================

async def get_completed_topics(telegram_id: int) -> list:
    """Get list of completed topics (legacy)"""
    user = await get_user(telegram_id)
    if user and user.get('completed_topics'):
        try:
            return json.loads(user['completed_topics'])
        except json.JSONDecodeError:
            return []
    return []

async def clear_completed_topics(telegram_id: int):
    """Clear completed topics (legacy)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET completed_topics = '[]' WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()

# ============================================================================
# CONVENIENCE / COMBINED OPERATIONS
# ============================================================================

async def get_db_state(telegram_id: int) -> dict:
    """
    Get complete DB state for backend routing.
    Combines HOT STATE + metadata.
    
    Returns:
        Dict with: grade, textbook, current_topic, current_checkpoint, mode, completed_topics
    """
    hot_state = await get_hot_state(telegram_id)
    completed = await get_completed_topics(telegram_id)
    
    return {
        **hot_state,
        'completed_topics': completed
    }

async def reset_user_progress(telegram_id: int):
    """
    Full reset: clear HOT STATE, WARM summary, and completed topics.
    Used for /reset command.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE users SET 
               current_topic = NULL,
               current_checkpoint = NULL,
               mode = NULL,
               warm_summary = NULL,
               completed_topics = '[]'
               WHERE telegram_id = ?""",
            (telegram_id,)
        )
        await db.commit()

async def get_all_users() -> list:
    """Get all user telegram IDs for broadcast"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_user_stats_summary() -> dict:
    """Get system-wide statistics for admin"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Total users
        async with db.execute("SELECT COUNT(*) as count FROM users") as cursor:
            total_users = (await cursor.fetchone())['count']
        
        # Total tokens consumed
        async with db.execute("SELECT SUM(tokens_used) as total FROM usage_log") as cursor:
            total_consumed = (await cursor.fetchone())['total'] or 0
        
        # Total tokens remaining
        async with db.execute("SELECT SUM(tokens) as total FROM users") as cursor:
            total_remaining = (await cursor.fetchone())['total'] or 0
        
        # Average messages today
        today = datetime.now().strftime('%Y-%m-%d')
        async with db.execute(
            "SELECT AVG(msg_count) as avg FROM (SELECT telegram_id, COUNT(*) as msg_count FROM usage_log WHERE DATE(timestamp) = ? GROUP BY telegram_id)",
            (today,)
        ) as cursor:
            avg_today = (await cursor.fetchone())['avg'] or 0
        
        return {
            'total_users': total_users,
            'total_tokens_consumed': total_consumed,
            'total_tokens_remaining': total_remaining,
            'avg_messages_today': round(avg_today, 1)
        }

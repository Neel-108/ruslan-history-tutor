# token_tracker.py
# RUSLAN v3.4 token tracking and management
# Real API token counts, tier tracking, no state mutations

import time
from typing import Dict

# ============================================================================
# CONSTANTS
# ============================================================================

INITIAL_TOKENS = 200_000
TOKEN_COST_PER_1K = 0.80  # For billing/display purposes

# ============================================================================
# TOKEN DISPLAY / UI HELPERS
# ============================================================================

def tokens_to_battery_bar(tokens: int) -> str:
    """Convert token count to visual battery bar"""
    percentage = (tokens / INITIAL_TOKENS) * 100
    if percentage >= 80:
        return "🟢🟢🟢🟢🟢"
    elif percentage >= 60:
        return "🟢🟢🟢🟢⚪"
    elif percentage >= 40:
        return "🟢🟢🟢⚪⚪"
    elif percentage >= 20:
        return "🟡🟡⚪⚪⚪"
    elif percentage > 0:
        return "🔴⚪⚪⚪⚪"
    else:
        return "⚫⚪⚪⚪⚪"

def format_battery_status(tokens: int) -> str:
    """
    Format battery status message for user.
    
    Args:
        tokens: Current token balance
        
    Returns:
        Formatted status string
    """
    if tokens is None:
        return "❌ Ошибка: пользователь не найден."
    
    battery = tokens_to_battery_bar(tokens)
    percentage = (tokens / INITIAL_TOKENS) * 100
    estimated_messages = tokens // 600  # Rough estimate
    
    message = f"""🔋 **Баланс токенов**
{battery} {percentage:.1f}%
📊 Токенов: {tokens:,} / {INITIAL_TOKENS:,}
💬 Примерно сообщений: ~{estimated_messages}
💡 *Каждый вопрос тратит ~600 токенов*
"""
    
    if tokens < 10_000:
        message += "\n⚠️ **Низкий баланс!** Пополните токены."
    
    return message

# ============================================================================
# TIER TRACKING (v3.4)
# ============================================================================

class TierTracker:
    """
    Track Tier-0, Tier-1, Tier-2 call distribution.
    
    Purpose:
    - Monitor token efficiency
    - Validate 65-70% token reduction
    - Debug routing decisions
    
    Does NOT:
    - Mutate user state
    - Make routing decisions
    - Modify token balances
    """
    
    def __init__(self):
        self.counts = {
            'tier_0_calls': 0,  # Backend only, no LLM
            'tier_1_calls': 0,  # Lite classifier
            'tier_2_calls': 0,  # Pro teaching
            'tier_1_tokens': 0,
            'tier_2_tokens': 0
        }
        self.start_time = time.time()
    
    def record_tier_0(self):
        """Record Tier-0 call (backend logic, no API)"""
        self.counts['tier_0_calls'] += 1
    
    def record_tier_1(self, tokens_used: int):
        """
        Record Tier-1 call (Lite classifier).
        
        Args:
            tokens_used: ACTUAL token count from API response
        """
        self.counts['tier_1_calls'] += 1
        self.counts['tier_1_tokens'] += tokens_used
    
    def record_tier_2(self, tokens_used: int):
        """
        Record Tier-2 call (Pro teaching).
        
        Args:
            tokens_used: ACTUAL token count from API response
        """
        self.counts['tier_2_calls'] += 1
        self.counts['tier_2_tokens'] += tokens_used
    
    def get_summary(self) -> Dict:
        """
        Get usage summary with percentages.
        
        Returns:
            Dict with tier breakdown and token reduction metrics
        """
        total_calls = sum([
            self.counts['tier_0_calls'],
            self.counts['tier_1_calls'],
            self.counts['tier_2_calls']
        ])
        
        total_tokens = self.counts['tier_1_tokens'] + self.counts['tier_2_tokens']
        
        # Calculate percentages
        tier_0_pct = (self.counts['tier_0_calls'] / max(total_calls, 1)) * 100
        tier_1_pct = (self.counts['tier_1_calls'] / max(total_calls, 1)) * 100
        tier_2_pct = (self.counts['tier_2_calls'] / max(total_calls, 1)) * 100
        
        # Average Pro tokens
        avg_tier_2_tokens = (
            self.counts['tier_2_tokens'] / max(self.counts['tier_2_calls'], 1)
        )
        
        # Token reduction vs baseline (v3.3 average was ~3500)
        baseline_avg = 3500
        reduction_pct = ((baseline_avg - avg_tier_2_tokens) / baseline_avg) * 100
        
        return {
            'total_calls': total_calls,
            'total_tokens': total_tokens,
            'tier_0_calls': self.counts['tier_0_calls'],
            'tier_1_calls': self.counts['tier_1_calls'],
            'tier_2_calls': self.counts['tier_2_calls'],
            'tier_0_percentage': round(tier_0_pct, 1),
            'tier_1_percentage': round(tier_1_pct, 1),
            'tier_2_percentage': round(tier_2_pct, 1),
            'avg_tier_2_tokens': round(avg_tier_2_tokens, 0),
            'token_reduction_percentage': round(reduction_pct, 1),
            'target_reduction_met': reduction_pct >= 65
        }
    
    def reset(self):
        """Reset all counters"""
        self.counts = {
            'tier_0_calls': 0,
            'tier_1_calls': 0,
            'tier_2_calls': 0,
            'tier_1_tokens': 0,
            'tier_2_tokens': 0
        }
        self.start_time = time.time()

# Module-level tracker instance
tier_tracker = TierTracker()

# ============================================================================
# TOKEN EXTRACTION HELPERS
# ============================================================================

def extract_yandex_tokens(api_response: dict, model_type: str = "pro") -> int:
    """
    Extract actual token count from YandexGPT API response.
    
    Args:
        api_response: Full API response dict
        model_type: "lite" or "pro"
        
    Returns:
        Token count from API or 0 if not found
    """
    try:
        # YandexGPT response structure
        # response['usage']['totalTokens'] or similar
        usage = api_response.get('usage', {})
        total_tokens = usage.get('totalTokens', 0)
        
        if total_tokens > 0:
            return total_tokens
        
        # Fallback: try alternative field names
        input_tokens = usage.get('inputTextTokens', 0)
        completion_tokens = usage.get('completionTokens', 0)
        
        return input_tokens + completion_tokens
        
    except Exception:
        # If extraction fails, return 0 (will be logged as error)
        return 0

def estimate_tokens_simple(text: str) -> int:
    """
    Simple token estimation (fallback only).
    Rule 10: Use actual API counts, not estimates.
    
    Args:
        text: Text to estimate
        
    Returns:
        Rough token count (1 token ≈ 4 chars)
    """
    return len(text) // 4

# ============================================================================
# GRADE-BASED TOKEN LIMITS
# ============================================================================

def get_max_tokens_for_grade(grade: int) -> int:
    """
    Get max output tokens for Pro calls based on grade.
    
    Younger grades get shorter responses.
    
    Args:
        grade: User's grade (5-11)
        
    Returns:
        Max tokens for Pro completion
    """
    limits = {
        5: 300,   # Grade 5: Simple, short
        6: 400,
        7: 500,
        8: 600,
        9: 700,
        10: 800,
        11: 1000  # Grade 11: More detailed
    }
    
    return limits.get(grade, 500)  # Default 500

# ============================================================================
# PENALTY TRACKING (Silent)
# ============================================================================

class PenaltyTracker:
    """
    Track silent penalties for abuse.
    Does NOT apply penalties (backend does that).
    Only logs for audit.
    """
    
    def __init__(self):
        self.penalties = []
    
    def record_penalty(self, user_id: int, penalty_type: str, tokens: int):
        """
        Record a penalty event.
        
        Args:
            user_id: User ID
            penalty_type: "abuse" or "spam"
            tokens: Tokens deducted
        """
        self.penalties.append({
            'user_id': user_id,
            'type': penalty_type,
            'tokens': tokens,
            'timestamp': time.time()
        })
    
    def get_user_penalties(self, user_id: int) -> list:
        """Get all penalties for user"""
        return [p for p in self.penalties if p['user_id'] == user_id]

# Module-level penalty tracker
penalty_tracker = PenaltyTracker()

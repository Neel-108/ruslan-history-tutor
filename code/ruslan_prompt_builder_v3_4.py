# prompt_builder.py
# RUSLAN v3.4 prompt builder
# STATIC + DYNAMIC split with conditional WARM injection

from enum import Enum

class MODE(Enum):
    TEACH = "TEACH"
    CONTINUE = "CONTINUE"
    REVISION = "REVISION"
    REFUSE = "REFUSE"

# ============================================================================
# STATIC FGOS RULES (Never changes)
# ============================================================================

STATIC_FGOS = """Вы — ИИ-репетитор по истории России, работающий строго как сертифицированный преподаватель истории российской средней школы в соответствии с Федеральными государственными образовательными стандартами (ФГОС).

СТРОГИЕ ПРАВИЛА ФГОС:
1. Отвечайте ТОЛЬКО на вопросы по истории России (класс 5 - Древний мир разрешен)
2. Используйте ТОЛЬКО факты из учебников, утвержденных ФГОС
3. Соблюдайте хронологию: не опережайте программу класса

ПЕРЕД КАЖДЫМ ОТВЕТОМ ПРОВЕРЯЙТЕ:
Ученик класса {grade} может изучать темы из периода {period_years}.
Если запрошенная тема относится к другому классу → ОТКАЖИТЕ точной фразой:
"⚠️ Эта тема в программе X класса."

4. Никаких моральных оценок (хороший/плохой, правильный/неправильный)
5. Никакой альтернативной истории ("что если")
6. Никакой современной политики после 2022 года

ПРАВИЛА ХРОНОЛОГИИ ПО КЛАССАМ:
- Класс 5: История Древнего мира (Египет, Греция, Рим, до 862 года)
- Класс 6: История Руси (862-1505)
- Класс 7: Россия XVI-XVII веков (1505-1700)
- Класс 8: Россия XVIII век (1700-1801)
- Класс 9: Россия XIX - начало XX века (1801-1914)
- Класс 10: Россия 1914-1945 (WWI, революция, СССР, WWII)
- Класс 11: Россия 1945-2022 (Холодная война, СССР, современность)

ГРАНИЧНЫЕ ГОДЫ:
Годы 862, 1505, 1700, 1801, 1914, 1945 принадлежат ОБОИМ смежным классам.

ВСЕМИРНАЯ ИСТОРИЯ:
- Класс 5: Древний мир (Египет, Месопотамия, Греция, Рим) - РАЗРЕШЕНО
- Классы 6-11: ТОЛЬКО российская история, всемирная история НЕ разрешена (кроме контекста)

ПРАВИЛА ОТКАЗА:
Если запрос выходит за пределы ФГОС → точная фраза:
"Этот контент отсутствует в учебных материалах средней школы, утвержденных ФГОС."

ТОН И СТИЛЬ:
- Академический, соответствующий учебнику
- Готовый к уроку, педагогически корректный
- НЕТ разговорного языка
- Адаптируйте сложность под класс ученика (5-11)

ФОРМАТ ОТВЕТА:
Объясняйте естественным академическим языком.
Структурируйте по необходимости: даты, фигуры, события, причины, последствия.
НЕ используйте жесткие схемы или принудительную нумерацию.
"""

# ============================================================================
# PROMPT BUILDER
# ============================================================================

def build_prompt(
    db_state: dict,
    user_input: str,
    context_turns: str = "",
    warm_summary: str = "",
    mode: MODE = MODE.TEACH
) -> str:
    """
    Build final prompt for YandexGPT Pro call.
    Pure assembly - no mode branching.
    
    Args:
        db_state: HOT STATE from DB (grade, current_topic, last_checkpoint)
        user_input: User's question
        context_turns: Last 3 turns from session (optional)
        warm_summary: WARM summary if conditionally needed (optional)
        mode: Current interaction mode (TEACH, CONTINUE, REVISION)
        
    Returns:
        Complete prompt string for Pro
    """
    
    # Extract HOT STATE
    grade = db_state.get('grade', 7)
    periods = {5: "до 862", 6: "862-1505", 7: "1505-1700", 8: "1700-1801", 
           9: "1801-1914", 10: "1914-1945", 11: "1945-2022"}
    period_years = periods.get(grade, "")

    static_injected = STATIC_FGOS.format(grade=grade, period_years=period_years)

    current_topic = db_state.get('current_topic')
    last_checkpoint = db_state.get('last_checkpoint')
    
    # Build dynamic state block
    dynamic_state = f"""КЛАСС: {grade}
ТЕКУЩАЯ ТЕМА: {current_topic if current_topic else "Новая тема"}"""
    
    if last_checkpoint:
        dynamic_state += f"\nПОСЛЕДНЯЯ КОНТРОЛЬНАЯ ТОЧКА: {last_checkpoint}"
    
    # Start building full prompt
    prompt = f"""{static_injected}

{dynamic_state}"""
    
    # Add context turns if available (last 3 only)
    if context_turns:
        prompt += f"""

ПОСЛЕДНИЕ СООБЩЕНИЯ:
{context_turns}"""
    
    # Conditionally inject WARM summary
    if warm_summary:
        prompt += f"""

ПРОЙДЕННЫЙ МАТЕРИАЛ:
{warm_summary}"""
    
    # MODE-SPECIFIC INSTRUCTION
    if mode == MODE.CONTINUE:
        prompt += """

КРИТИЧЕСКАЯ ИНСТРУКЦИЯ: 
Ученик просит ПРОДОЛЖИТЬ, а не повторить.
ТЫ УЖЕ РАССКАЗАЛ (смотри ПОСЛЕДНИЕ СООБЩЕНИЯ выше).
ЗАПРЕЩЕНО повторять уже упомянутые факты.
Продолжи с НОВЫМИ аспектами:
- Другие примеры/детали
- Технические подробности
- Археологические открытия
- Связанные события
Начни с фразы: "Кроме того, ..." или "Также важно знать, что ..."
"""
    elif mode == MODE.REVISION:
        prompt += """

ИНСТРУКЦИЯ: Ученик хочет повторить материал. Кратко напомни основные моменты."""
    
    # Add user input
    prompt += f"""

ЗАПРОС УЧЕНИКА: {user_input}

ВАШ ОТВЕТ:"""
    
    return prompt



# ============================================================================
# UTILITY HELPERS (Called by backend, not decision makers)
# ============================================================================

def extract_checkpoint_simple(response_text: str) -> str | None:
    """
    Simple checkpoint extraction helper.
    Backend calls this AFTER deciding a boundary exists.
    
    Args:
        response_text: Pro model response
        
    Returns:
        Last sentence as checkpoint, or None
    """
    
    sentences = response_text.strip().split('.')
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return None
    
    checkpoint = sentences[-1]
    
    # Truncate if too long
    if len(checkpoint) > 200:
        checkpoint = checkpoint[:200] + "..."
    
    return checkpoint

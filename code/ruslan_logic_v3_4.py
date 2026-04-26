# ruslan_logic.py
# RUSLAN v3.4 FGOS validation layer
# Pure content validation - NO routing, NO mode decisions, NO state mutations

import re
from typing import Tuple, Optional

class RuslanLogic:
    """
    FGOS 2024+ curriculum validation.
    
    Responsibilities:
    - Chronology validation (grade-to-period mapping)
    - Curriculum scope checks (FGOS boundaries)
    - Refusal rules (moral judgments, homework, post-2022, etc.)
    
    NOT responsible for:
    - Mode decisions (backend owns)
    - Routing (backend owns)
    - Abuse handling (backend owns)
    - Continuation detection (backend owns)
    """
    
    def __init__(self):
        # FGOS 2024+ official grade-to-period mapping
        self.grade_periods = {
            5: ("История Древнего мира", 0, 861),
            6: ("История Руси (с древнейших времён до конца XV века)", 862, 1505),
            7: ("Россия в XVI–XVII веках", 1505, 1700),
            8: ("Россия в XVIII веке", 1700, 1801),
            9: ("Россия в XIX – начале XX века", 1801, 1914),
            10: ("Россия в 1914–1945 годах", 1914, 1945),
            11: ("Россия с 1945 года по настоящее время", 1945, 2022)
        }
        
        # Russian history topics - year mapping
        self.topic_years = {
            # Grade 6: История Руси (862-1505)
            "рюрик": 862, "призвание варягов": 862, "полюдье": 862,
            "киевская русь": 988, "владимир": 988, "крещение руси": 988,
            "ярослав мудрый": 1019, "русская правда": 1016,
            "юрий долгорукий": 1125, "андрей боголюбский": 1157,
            "батый": 1237, "монгольское нашествие": 1237, "золотая орда": 1243,
            "александр невский": 1240, "невская битва": 1240, "ледовое побоище": 1242,
            "иван калита": 1325, "дмитрий донской": 1359, "куликовская битва": 1380,
            "иван третий": 1462, "иван iii": 1462, "стояние на угре": 1480,
            "судебник": 1497, "василий третий": 1505,
            
            # Grade 7: Россия XVI-XVII веков (1505-1700)
            "иван грозный": 1547, "иван четвертый": 1547, "иван iv": 1547,
            "венчание на царство": 1547, "избранная рада": 1549,
            "судебник 1550": 1550, "казанское ханство": 1552, "опричнина": 1565,
            "борис годунов": 1598, "смутное время": 1598, "смута": 1598,
            "лжедмитрий": 1605, "василий шуйский": 1606,
            "минин и пожарский": 1612, "освобождение москвы": 1612,
            "михаил романов": 1613, "романовы": 1613,
            "алексей михайлович": 1645, "соборное уложение": 1649,
            "церковный раскол": 1653, "никон": 1653, "старообрядцы": 1653,
            "степан разин": 1670, "разин": 1670, "петр первый": 1682,
            
            # Grade 8: Россия в XVIII веке (1700-1801)
            "северная война": 1700, "полтавская битва": 1709,
            "ништадтский мир": 1721, "российская империя": 1721,
            "табель о рангах": 1722, "екатерина первая": 1725,
            "анна иоанновна": 1730, "бироновщина": 1730,
            "елизавета петровна": 1741, "ломоносов": 1741,
            "екатерина вторая": 1762, "екатерина ii": 1762,
            "пугачев": 1773, "пугачевское восстание": 1773,
            "присоединение крыма": 1783, "суворов": 1790,
            "павел первый": 1796, "павел i": 1796,
            
            # Grade 9: Россия в XIX - начале XX века (1801-1914)
            "александр первый": 1801, "александр i": 1801,
            "отечественная война": 1812, "бородино": 1812, "кутузов": 1812,
            "декабристы": 1825, "восстание декабристов": 1825,
            "николай первый": 1825, "николай i": 1825,
            "крымская война": 1853, "оборона севастополя": 1854,
            "александр второй": 1855, "александр ii": 1855,
            "отмена крепостного": 1861, "крестьянская реформа": 1861,
            "земская реформа": 1864, "судебная реформа": 1864,
            "народники": 1870, "народная воля": 1879,
            "александр третий": 1881, "контрреформы": 1881,
            "николай второй": 1894, "николай ii": 1894,
            "революция 1905": 1905, "кровавое воскресенье": 1905,
            "столыпин": 1906, "столыпинская реформа": 1906,
            
            # Grade 10: Россия 1914-1945
            "первая мировая": 1914, "брусиловский прорыв": 1916,
            "февральская революция": 1917, "октябрьская революция": 1917,
            "ленин": 1917, "временное правительство": 1917,
            "гражданская война": 1918, "красные": 1918, "белые": 1918,
            "колчак": 1918, "деникин": 1919, "врангель": 1920,
            "нэп": 1921, "образование ссср": 1922, "сталин": 1924,
            "индустриализация": 1928, "коллективизация": 1929,
            "репрессии": 1937, "большой террор": 1937,
            "пакт молотова риббентропа": 1939, "советско финская война": 1939,
            "великая отечественная": 1941, "вов": 1941, "22 июня": 1941,
            "блокада ленинграда": 1941, "битва за москву": 1941,
            "сталинградская битва": 1942, "курская битва": 1943,
            "день победы": 1945, "9 мая": 1945,
            
            # Grade 11: Россия 1945-2022
            "холодная война": 1946, "план маршалла": 1947,
            "хрущев": 1953, "оттепель": 1953, "xx съезд": 1956,
            "целина": 1954, "карибский кризис": 1962,
            "брежнев": 1964, "застой": 1964, "пражская весна": 1968,
            "афганская война": 1979, "горбачев": 1985, "перестройка": 1985,
            "путч": 1991, "распад ссср": 1991, "ельцин": 1991,
            "дефолт": 1998, "путин": 2000, "крым": 2014,
        }
        
        # World history keywords (Grade 5 allowed, others blocked)
        self.world_history_keywords = [
            "древний египет", "египет", "фараон", "пирамид", "сфинкс",
            "древняя греция", "спарта", "афины", "александр македонский",
            "древний рим", "цезарь", "октавиан", "римская империя",
            "месопотамия", "вавилон", "хаммурапи",
        ]
        
        # FGOS refusal keywords
        self.post_2022_keywords = [
            "2023", "2024", "2025", "2026",
            "украина", "сво", "специальная военная операция",
        ]
        
        self.homework_patterns = [
            "напиши сочинение", "реши задание", "дай ответ на",
            "помоги с домашкой", "сделай за меня", "выполни за меня",
        ]
        
        self.moral_keywords = [
            "хорошо или плохо", "правильно поступил", "виноват ли",
            "оправдан ли", "кто прав", "можно ли осуждать",
            "хорошим царём", "плохим правителем", "добрый царь", "злой царь",
        ]
        
        self.alt_history = [
            "что если", "а если бы", "альтернатива",
            "что было бы если", "альтернативная история",
        ]
        
        self.historiography_keywords = [
            "какие историки", "историки изучали", "историография",
            "мнения историков", "ключевский", "соловьев",
        ]
    
    # ========================================================================
    # PURE VALIDATION METHODS (No decisions, no routing)
    # ========================================================================
    
        # """
        # Extract historical year from question by matching known topics.
        
        # Returns:
            # Year or None if topic not recognized
        # """
        
    def parse_topic_year(self, question: str) -> Optional[int]:
        q_lower = question.lower()
    
        for topic, year in self.topic_years.items():
            # Use word boundaries for short keywords (≤3 chars)
            if len(topic) <= 3:
                pattern = r'\b' + re.escape(topic) + r'\b'
                if re.search(pattern, q_lower):
                    return year
            else:
                # Substring match for longer keywords
                if topic in q_lower:
                    return year
        
        return None

    
    def check_fgos_refusal(self, question: str, grade: int) -> Tuple[bool, str]:
        """
        Check if question violates FGOS rules.
        
        Returns:
            (should_refuse: bool, refusal_message: str)
        """
        q_lower = question.lower()
        
        # Check post-2022 events
        for keyword in self.post_2022_keywords:
            if keyword in q_lower:
                return (True, "⚠️ Эта тема выходит за границы школьной программы (до 2022).")
        
        # Check homework requests
        for pattern in self.homework_patterns:
            if pattern in q_lower:
                return (True, "Я не могу решать задания напрямую. Какая тема вам нужна?")
        
        # Check moral judgments
        for keyword in self.moral_keywords:
            if keyword in q_lower:
                return (True, "⚠️ Я не оцениваю исторические события как 'хорошо' или 'плохо'.")
        
        # Check alternative history
        for keyword in self.alt_history:
            if keyword in q_lower:
                return (True, "⚠️ Альтернативная история не входит в программу.")
        
        # Check historiography
        for keyword in self.historiography_keywords:
            if keyword in q_lower:
                return (True, "⚠️ Я изучаю факты, а не споры историков.")
        
        # # Grade 5 special case: block Russian history
        # if grade == 5:
            # for topic in self.topic_years.keys():
                # if topic in q_lower:
                    # return (True, "⚠️ В 5 классе изучаем Древний мир! Русская история начнётся в 6 классе.")
        
        # Grades 6-11: block world history unless contextual
        if grade >= 6:
            russian_topic_found = any(topic in q_lower for topic in self.topic_years.keys())
            
            if not russian_topic_found:
                for world_topic in self.world_history_keywords:
                    if world_topic in q_lower:
                        return (True, "⚠️ Я специализируюсь на истории России!")
        
        return (False, "")
    
    def check_grade_chronology(self, question: str, grade: int) -> Tuple[bool, str]:
        """
        Check if topic matches grade chronology.
        
        Returns:
            (is_allowed: bool, refusal_message: str)
        """
        if grade not in self.grade_periods:
            return (True, "")
        
        period_name, start_year, end_year = self.grade_periods[grade]
        topic_year = self.parse_topic_year(question)
        
        # If can't determine year, allow (might be general question)
        if topic_year is None:
            return (True, "")
        
        # Check chronology (boundary years allowed for both adjacent grades)
        if not (start_year <= topic_year <= end_year):
            if topic_year > end_year:
                future_grade = None
                for g, (_, g_start, g_end) in self.grade_periods.items():
                    if g_start <= topic_year <= g_end:
                        future_grade = g
                        break
                
                if future_grade:
                    return (False, f"⚠️ Эта тема в программе {future_grade} класса.")
                else:
                    return (False, "⚠️ Эта тема выходит за границы программы.")
            else:
                return (False, "⚠️ Мы уже прошли эту тему! Хотите повторить?")
        
        return (True, "")
    
    
    def validate_question(self, question: str, grade: int) -> Tuple[bool, str]:
        # Step 1: Hard refusals (all grades)
        should_refuse, msg = self.check_fgos_refusal(question, grade)
        if should_refuse:
            return (False, msg)
        
        # Step 2: Grade 5 special logic
        if grade == 5:
            topic_year = self.parse_topic_year(question)
            # print(f"DEBUG: Grade 5 question: {question}")
            # print(f"DEBUG: Detected year: {topic_year}")
            
            if topic_year is not None:
                # Russian history keyword found
                return (False, "⚠️ В 5 классе изучаем Древний мир! Русская история начнётся в 6 классе.")
            
            # No Russian keyword = world history subtopic
            return (True, "")
        
        # Step 3: Grades 6-11 chronology
        return self.check_grade_chronology(question, grade)

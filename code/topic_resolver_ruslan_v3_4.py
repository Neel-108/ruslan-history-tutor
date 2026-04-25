"""
topic_resolver.py
Deterministic topic resolution using FGOS canonical topics
Loads JSON at startup, provides alias matching and grade enforcement
"""

import json
import re
import logging
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

class TopicResolver:
    """
    Resolves user queries to canonical FGOS topics
    Based on fgos_history_canonical_topics_5-11_v1.json
    """
    
    def __init__(self, json_path: str = "fgos_history_canonical_topics_5-11_v1.json"):
        """Load canonical topics and build alias lookup"""
        self.topics = []
        self.alias_map = {}  # lowercase alias -> canonical_topic
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.topics = json.load(f)
            
            # Build alias map
            for topic_data in self.topics:
                canonical = topic_data['canonical_topic']
                grade = topic_data['grade']
                
                # Add all aliases
                for alias in topic_data.get('aliases', []):
                    normalized = self._normalize(alias)
                    if normalized not in self.alias_map:
                        self.alias_map[normalized] = []
                    self.alias_map[normalized].append({
                        'canonical_topic': canonical,
                        'grade': grade,
                        'year_start': topic_data.get('year_start'),
                        'year_end': topic_data.get('year_end')
                    })
            
            logger.info(f"Loaded {len(self.topics)} canonical topics with {len(self.alias_map)} aliases")
            
        except FileNotFoundError:
            logger.error(f"Canonical topics JSON not found: {json_path}")
            self.topics = []
            self.alias_map = {}
    
    def _normalize(self, text: str) -> str:
        """Normalize text: lowercase, strip punctuation, collapse whitespace"""
        text = text.lower()
        text = re.sub(r'[^wа-яёs]', '', text, flags=re.UNICODE)
        text = re.sub(r's+', ' ', text).strip()
        return text
    
    def resolve_topic(self, user_query: str, user_grade: int) -> Tuple[Optional[str], bool, str]:
        """
        Resolve user query to canonical topic
        
        Args:
            user_query: User's question text
            user_grade: User's grade (5-11)
            
        Returns:
            (canonical_topic, is_valid, message)
            
            canonical_topic: Resolved topic name or None
            is_valid: True if topic matches user's grade, False if grade mismatch
            message: Refusal message if grade mismatch, empty if valid
        """
        
        if not self.alias_map:
            # No topics loaded - allow any query (graceful degradation)
            return (None, True, "")
        
        # Extract candidate keywords from query
        normalized_query = self._normalize(user_query)
        words = normalized_query.split()
        
        # Try to match aliases (prefer longer matches first)
        matches = []
        
        # Try 3-word phrases
        for i in range(len(words) - 2):
            phrase = " ".join(words[i:i+3])
            if phrase in self.alias_map:
                matches.extend(self.alias_map[phrase])
        
        # Try 2-word phrases
        for i in range(len(words) - 1):
            phrase = " ".join(words[i:i+2])
            if phrase in self.alias_map:
                matches.extend(self.alias_map[phrase])
        
        # Try single words
        for word in words:
            if word in self.alias_map:
                matches.extend(self.alias_map[word])
        
        if not matches:
            # No alias matched - allow query (out of curriculum, but not blocked)
            logger.info(f"No topic resolved for: {user_query[:50]}")
            return (None, True, "")
        
        # Filter matches by grade
        grade_matches = [m for m in matches if m['grade'] == user_grade]
        
        if grade_matches:
            # Found topic matching user's grade
            canonical_topic = grade_matches[0]['canonical_topic']
            logger.info(f"Resolved topic: {canonical_topic} (grade {user_grade})")
            return (canonical_topic, True, "")
        
        # Topic found but grade mismatch
        wrong_grade_topic = matches[0]
        refusal_msg = (
            f"Тема \"{wrong_grade_topic['canonical_topic']}\" изучается в "
            f"{wrong_grade_topic['grade']} классе. "
            f"Сейчас ты в {user_grade} классе. Задай вопрос по программе своего класса."
        )
        
        logger.warning(f"Grade mismatch: {wrong_grade_topic['canonical_topic']} "
                      f"(grade {wrong_grade_topic['grade']}) for user grade {user_grade}")
        
        return (wrong_grade_topic['canonical_topic'], False, refusal_msg)


# Module-level singleton
_resolver = None

def get_topic_resolver() -> TopicResolver:
    """Get or create topic resolver singleton"""
    global _resolver
    if _resolver is None:
        _resolver = TopicResolver()
    return _resolver
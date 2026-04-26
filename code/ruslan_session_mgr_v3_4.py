"""
session_mgr_v3_4.py
RUSLAN v3.4 session manager
Last 3 turns ONLY - stores CHECKPOINTS not full answers (Issue 3 fix)
"""

from typing import Dict, List, Tuple
import time

class SessionManager:
    """
    Manages last 3 conversation turns per user.
    
    Rules (v3.4):
    - Session is NOT memory
    - Keeps only last 3 user-bot pairs
    - Stores CHECKPOINT (50-80 tokens) instead of full answer (300 tokens)
    - Used for pronoun resolution and disambiguation only
    - No summarization
    - No state decisions
    """
    
    def __init__(self):
        self.sessions: Dict[int, List[Tuple[str, str, float]]] = {}  # user_id: [(question, checkpoint, timestamp)]
        self.session_timeout = 30 * 60  # 30 minutes
    
    def add_message(self, user_id: int, question: str, answer_checkpoint: str):
        """
        Add a Q&A pair to user's session.
        Automatically keeps only last 3 turns.
        
        Args:
            user_id: User identifier
            question: User's question
            answer_checkpoint: Checkpoint from bot's answer (NOT full answer)
        """
        if user_id not in self.sessions:
            self.sessions[user_id] = []
        
        # Truncate checkpoint if still too long (defensive)
        if len(answer_checkpoint) > 200:
            answer_checkpoint = answer_checkpoint[:197] + "..."
        
        # Add new message with timestamp
        self.sessions[user_id].append((question, answer_checkpoint, time.time()))
        
        # Keep only last 3 turns (HARD LIMIT)
        if len(self.sessions[user_id]) > 3:
            self.sessions[user_id] = self.sessions[user_id][-3:]
    
    def get_recent_turns(self, user_id: int, n_turns: int = 3) -> str:
        """
        Get last N turns formatted for context.
        
        Args:
            user_id: User identifier
            n_turns: Number of recent turns (default 3, max 3)
            
        Returns:
            Formatted string of recent Q&A or empty string if none
        """
        # Enforce hard limit: max 3 turns
        n_turns = min(n_turns, 3)
        
        if user_id not in self.sessions:
            return ""
        
        session = self.sessions[user_id]
        
        # Check if session expired
        if session and (time.time() - session[-1][2]) > self.session_timeout:
            self.clear_session(user_id)
            return ""
        
        # Get last N turns
        recent = session[-n_turns:] if len(session) >= n_turns else session
        
        if not recent:
            return ""
        
        # Format as simple Q&A (using checkpoint, not full answer)
        formatted = []
        for question, checkpoint, _ in recent:
            formatted.append(f"Вопрос: {question}\nОтвет: {checkpoint}")
        
        return "\n\n".join(formatted)
    
    def clear_session(self, user_id: int):
        """Clear user's session"""
        if user_id in self.sessions:
            del self.sessions[user_id]
    
    def get_turn_count(self, user_id: int) -> int:
        """
        Get number of turns in current session.
        
        Returns:
            Number of turns (0-3)
        """
        if user_id not in self.sessions:
            return 0
        return len(self.sessions[user_id])
    
    def is_session_active(self, user_id: int) -> bool:
        """
        Check if user has an active session.
        
        Returns:
            True if session exists and not expired
        """
        if user_id not in self.sessions:
            return False
        
        session = self.sessions[user_id]
        if not session:
            return False
        
        # Check expiration
        if (time.time() - session[-1][2]) > self.session_timeout:
            self.clear_session(user_id)
            return False
        
        return True

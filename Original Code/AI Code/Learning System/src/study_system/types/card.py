"""Pydantic types for FSRS scheduling."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class CardType(str, Enum):
    flashcard = "flashcard"
    formula = "formula"
    quiz_mcq = "quiz_mcq"
    quiz_short = "quiz_short"


class FSRSState(BaseModel):
    """Full FSRS card state. All fields mirror FSRS-4.5 parameter names."""

    stability: float = 0.0  # S — expected days to 90% retention
    difficulty: float = 5.0  # D — card difficulty on FSRS scale 1-10
    elapsed_days: int = 0
    scheduled_days: int = 0
    reps: int = 0
    lapses: int = 0
    state: str = "new"  # 'new' | 'learning' | 'review' | 'relearning'
    next_due_at: Optional[datetime] = None


class CardRating(int, Enum):
    again = 1
    hard = 2
    good = 3
    easy = 4

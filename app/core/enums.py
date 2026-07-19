"""Shared enumerations for Project Atlas."""

from enum import Enum


class InputType(str, Enum):
    """Supported project input types."""

    TOPIC = "topic"
    YOUTUBE_URL = "youtube_url"
    NEWS_URL = "news_url"
    TRANSCRIPT = "transcript"


class ClaimStatus(str, Enum):
    """Verification status assigned to a claim."""

    CONFIRMED = "confirmed"
    REPORTED = "reported"
    OPINION = "opinion"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"


class ScriptSection(str, Enum):
    """Documentary script section identifiers."""

    HOOK = "hook"
    BACKGROUND = "background"
    CURRENT_SITUATION = "current_situation"
    ANALYSIS = "analysis"
    POSSIBLE_OUTCOMES = "possible_outcomes"
    CONCLUSION = "conclusion"


class AgentName(str, Enum):
    """Registered agent identifiers."""

    RESEARCH = "research"
    FACT_CHECK = "fact_check"
    SCRIPT_WRITER = "script_writer"
    STORYBOARD = "storyboard"
    VISUAL_DIRECTOR = "visual_director"
    PUBLISHER = "publisher"

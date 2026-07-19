"""Application-wide constants."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"
DATA_DIR = PROJECT_ROOT / "data"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = DATA_DIR / "cache"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
PROMPTS_DIR = APP_DIR / "prompts"
TEMPLATES_DIR = APP_DIR / "templates"

RESEARCH_SUBDIR = "research"
SCRIPT_SUBDIR = "script"
STORYBOARD_SUBDIR = "storyboard"
VISUALS_SUBDIR = "visuals"
SEO_SUBDIR = "seo"

RESEARCH_FILES = (
    "summary.md",
    "timeline.md",
    "entities.md",
    "relations.md",
    "claims.md",
    "sources.md",
    "questions.md",
)

FACT_CHECK_FILENAME = "fact_check.md"
SCRIPT_FILENAME = "documentary_script.md"

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_LOG_LEVEL = "INFO"

"""Text utility functions."""


def truncate(text: str, max_length: int = 200) -> str:
    """Truncate text to a maximum length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."

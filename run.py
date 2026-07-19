"""CLI entry point for Project Atlas."""

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from app.core.config import get_settings
from app.core.enums import InputType
from app.core.logger import setup_logging
from app.models.project import ProjectInput
from app.pipelines.atlas_pipeline import AtlasPipeline

console = Console()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Project Atlas — AI geopolitical documentary generation platform.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topic", type=str, help="Research topic string.")
    group.add_argument("--youtube-url", type=str, help="YouTube video URL.")
    group.add_argument("--news-url", type=str, help="News article URL.")
    group.add_argument("--transcript", type=str, help="Transcript text or file path.")
    parser.add_argument("--title", type=str, default=None, help="Optional project title.")
    parser.add_argument("--phase", type=int, default=1, help="Pipeline phase to run (default: 1).")
    return parser


def resolve_input(args: argparse.Namespace) -> ProjectInput:
    """Convert CLI arguments to a ProjectInput model."""
    if args.topic:
        return ProjectInput(input_type=InputType.TOPIC, content=args.topic, title=args.title)
    if args.youtube_url:
        return ProjectInput(
            input_type=InputType.YOUTUBE_URL,
            content=args.youtube_url,
            title=args.title,
        )
    if args.news_url:
        return ProjectInput(
            input_type=InputType.NEWS_URL,
            content=args.news_url,
            title=args.title,
        )
    content = args.transcript
    if content and len(content) < 260:
        from pathlib import Path

        path = Path(content)
        if path.exists():
            content = path.read_text(encoding="utf-8")
    return ProjectInput(input_type=InputType.TRANSCRIPT, content=content, title=args.title)


def main() -> int:
    """CLI main function."""
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    project_input = resolve_input(args)
    pipeline = AtlasPipeline(settings)
    result = pipeline.run(project_input, phase=args.phase)

    console.print(
        Panel.fit(
            f"[bold green]Phase {args.phase} complete[/bold green]\n\n"
            f"Project: [cyan]{result.slug}[/cyan]\n"
            f"Output:  [cyan]{result.project_dir}[/cyan]",
            title="Project Atlas",
        )
    )
    for note in result.notes:
        console.print(f"  • {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

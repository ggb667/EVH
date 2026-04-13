#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def configure_import_path(script_path: Path) -> None:
    project_vendor = script_path.resolve().parents[1] / "vendor"
    if str(project_vendor) not in sys.path:
        sys.path.insert(0, str(project_vendor))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--personality", required=True)
    parser.add_argument("--workfile", required=True)
    parser.add_argument("--draft-path", required=True)
    parser.add_argument("--notice-path", required=True)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--result-path", required=True)
    return parser.parse_args()


def prompt_label_for(personality: str) -> str:
    labels = {
        "PRINCESS_CELESTIA_SOL_INVICTUS": "Princess Celestia Sol Invictus",
        "TWILIGHT_SPARKLE": "✶ Twilight",
        "APPLEJACK": "🍎 Applejack",
        "PINKIE_PIE": "🎈 Pinkie",
        "RARITY": "💎 Rarity",
        "FLUTTERSHY": "🦋 Fluttershy",
        "RAINBOW_DASH": "⚡ Rainbow Dash",
        "SPIKE": "🐲 Spike",
    }
    return labels.get(personality, personality)


def celestia_prompt_fragments() -> list[tuple[str, str]]:
    colors = ["#3D9DC4", "#48BAA9", "#7A9BDE", "#D085D0"]
    title = "Princess Celestia Sol Invictus"
    fragments: list[tuple[str, str]] = [("fg:#3D9DC4 bold", "☀ ")]
    color_index = 0
    pair_index = 0
    current_text = ""

    def flush_current_text() -> None:
        nonlocal current_text
        if not current_text:
            return
        fragments.append((f"fg:{colors[color_index]} bold", current_text))
        current_text = ""

    for char in title:
        if char.isspace():
            flush_current_text()
            fragments.append(("class:prompt", char))
            continue
        current_text += char
        pair_index += 1
        if pair_index == 2:
            flush_current_text()
            pair_index = 0
            color_index = (color_index + 1) % len(colors)

    flush_current_text()
    fragments.append(("class:prompt", " > "))
    return fragments


def prompt_fragments_for(personality: str) -> list[tuple[str, str]]:
    if personality == "PRINCESS_CELESTIA_SOL_INVICTUS":
        return celestia_prompt_fragments()
    return [("class:prompt", f"{prompt_label_for(personality)} > ")]


def main() -> int:
    script_path = Path(__file__)
    configure_import_path(script_path)

    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style

    args = parse_args()
    draft_path = Path(args.draft_path)
    notice_path = Path(args.notice_path)
    history_path = Path(args.history_path)
    result_path = Path(args.result_path)

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    draft_text = draft_path.read_text() if draft_path.exists() else ""
    notice_text = notice_path.read_text().strip() if notice_path.exists() else ""

    style = Style.from_dict(
        {
            "prompt": "bold",
            "toolbar": "reverse",
        }
    )

    toolbar = notice_text or "Enter submits to the parked pony session. Ctrl-C leaves the session parked."
    session = PromptSession(history=FileHistory(str(history_path)))
    try:
      text = session.prompt(
          prompt_fragments_for(args.personality),
          default=draft_text,
          style=style,
          bottom_toolbar=toolbar,
          multiline=True,
      )
    except KeyboardInterrupt:
      return 130
    except EOFError:
      return 130

    draft_path.write_text(text)
    result_path.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
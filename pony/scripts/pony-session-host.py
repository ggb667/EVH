#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
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
    parser.add_argument("--rootdir", required=True)
    parser.add_argument("--promptfile", required=True)
    parser.add_argument("--session-name", required=True)
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--draft-path", required=True)
    parser.add_argument("--notice-path", required=True)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--queue-script", required=True)
    parser.add_argument("--codex-wrapper", required=True)
    parser.add_argument("--monitor-script", required=True)
    parser.add_argument("--idle-sentinel", default="")
    parser.add_argument("--partial-idle-sentinel", default="Ω")
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


def dirty_fix_first_prompt(project_root: str, initial_prompt: str) -> str:
    cleanup_prompt = (
        f"Coordinator preflight detected a dirty worktree in {project_root}. "
        "First, inspect and reconcile or put away the pending local changes in that repo. "
        "Do not ignore them or defer that cleanup. After the worktree is in a deliberate state, "
        "continue with normal Twilight coordination behavior."
    )
    if initial_prompt:
        return f"{cleanup_prompt}\n\n{initial_prompt}"
    return cleanup_prompt


class PonySessionHost:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.rootdir = Path(args.rootdir)
        self.promptfile = Path(args.promptfile)
        self.draft_path = Path(args.draft_path)
        self.notice_path = Path(args.notice_path)
        self.history_path = Path(args.history_path)
        self.session_name = args.session_name
        self.socket_path = Path(args.socket_path)
        self.queue_script = args.queue_script
        self.codex_wrapper = args.codex_wrapper
        self.monitor_script = args.monitor_script
        self.idle_sentinel = args.idle_sentinel
        self.partial_idle_sentinel = args.partial_idle_sentinel
        self.initial_prompt = self.promptfile.read_text() if self.promptfile.exists() else ""
        self.personality = args.personality
        self.bootstrap_profile, self.bootstrap_prompt, self.startup_action = self._resolve_preflight()

    def tmux(self, *subcmd: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = ["tmux", "-S", str(self.socket_path), *subcmd]
        return subprocess.run(
            cmd,
            text=True,
            capture_output=capture,
            check=check,
        )

    def _resolve_preflight(self) -> tuple[str | None, str, str]:
        preflight = subprocess.run(
            [self.args.queue_script.replace("queue-runtime.sh", "worker-preflight.sh"), self.personality, self.args.workfile, self.args.rootdir],
            text=True,
            capture_output=True,
            check=False,
            cwd=self.rootdir,
        )
        result = preflight.stdout.strip() or "ESCALATE_TWI"
        if result == "READY_NO_LLM":
            return None, self.initial_prompt, "launch"
        if result == "BLOCKED_DIRTY_FIX_FIRST":
            if self.personality in {"TWILIGHT_SPARKLE", "PRINCESS_CELESTIA_SOL_INVICTUS"}:
                return "twi_coordinator", dirty_fix_first_prompt(self.args.rootdir, self.initial_prompt), "launch"
            return None, "Only Twilight may continue from BLOCKED_DIRTY_FIX_FIRST.", "editor_only"
        if result == "ESCALATE_MINI":
            return "worker_mini", self.initial_prompt, "launch"
        if result == "ESCALATE_TWI":
            if self.personality in {"TWILIGHT_SPARKLE", "PRINCESS_CELESTIA_SOL_INVICTUS"}:
                return "twi_coordinator", self.initial_prompt, "launch"
            return None, "Preflight: ESCALATE_TWI. Worker Codex not launched.", "editor_only"
        return None, f"Preflight error: unexpected result '{result}'.", "editor_only"

    def session_exists(self) -> bool:
        return self.tmux("has-session", "-t", self.session_name, check=False).returncode == 0

    def kill_existing_session(self) -> None:
        if self.session_exists():
            self.tmux("kill-session", "-t", self.session_name, check=False)

    def current_pane_id(self) -> str:
        result = self.tmux("display-message", "-p", "-t", self.session_name, "#{pane_id}", capture=True)
        return result.stdout.strip()

    def create_session(self, bootstrap_prompt: str, profile: str | None) -> None:
        env_pairs = {
            "PERSONALITY": self.personality,
            "WORKING_ON": self.args.workfile,
            "CODEX_PONY_IDLE_MONITOR_SCRIPT": self.monitor_script,
            "CODEX_PONY_TMUX_SOCKET_PATH": str(self.socket_path),
            "CODEX_PONY_IDLE_SENTINEL": self.idle_sentinel,
            "CODEX_PONY_PARTIAL_IDLE_SENTINEL": self.partial_idle_sentinel,
            "CODEX_PONY_IDLE_ACTION": "detach-client",
        }
        wrapper_parts = [shlex.quote(self.codex_wrapper)]
        if profile:
            wrapper_parts.extend(["-p", shlex.quote(profile)])
        if bootstrap_prompt:
            wrapper_parts.append(shlex.quote(bootstrap_prompt))
        shell_cmd = (
            f"cd {shlex.quote(str(self.rootdir))} && "
            f"exec env {' '.join(f'{key}={shlex.quote(value)}' for key, value in env_pairs.items())} "
            f"{' '.join(wrapper_parts)}"
        )
        self.tmux("new-session", "-d", "-s", self.session_name, shell_cmd)

    def attach(self) -> None:
        self.tmux("attach-session", "-t", self.session_name, check=False)

    def send_prompt(self, text: str) -> None:
        pane_id = self.current_pane_id()
        self.tmux("send-keys", "-t", pane_id, "-l", text)
        self.tmux("send-keys", "-t", pane_id, "Enter")

    def read_notice(self) -> str:
        if self.notice_path.exists():
            return self.notice_path.read_text().strip()
        return ""

    def prompt_loop(self) -> int:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.styles import Style

        self.draft_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        style = Style.from_dict({"prompt": "bold", "toolbar": "reverse"})
        session = PromptSession(history=FileHistory(str(self.history_path)))
        if self.startup_action == "launch":
            self.kill_existing_session()
            self.create_session(self.bootstrap_prompt, self.bootstrap_profile)
            self.attach()

        while True:
            default_text = self.draft_path.read_text() if self.draft_path.exists() else ""
            notice_text = self.read_notice()
            toolbar = notice_text or "Enter submits to the parked pony session. Ctrl-C exits the host."
            try:
                text = session.prompt(
                    prompt_fragments_for(self.personality),
                    default=default_text,
                    style=style,
                    bottom_toolbar=toolbar,
                    multiline=True,
                )
            except KeyboardInterrupt:
                return 130
            except EOFError:
                return 130

            self.draft_path.write_text(text)
            if not text.strip():
                continue

            if not self.session_exists():
                self.create_session("", self.bootstrap_profile)
            self.send_prompt(text)
            self.attach()


def main() -> int:
    script_path = Path(__file__)
    configure_import_path(script_path)
    args = parse_args()
    host = PonySessionHost(args)
    return host.prompt_loop()


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import os
import sys
from typing import Sequence


def width() -> int:
    return max(64, min(96, os.get_terminal_size().columns if sys.stdout.isatty() else 78))


def rule(char: str = "-") -> str:
    return char * width()


def header(title: str, subtitle: str | None = None) -> None:
    print(rule("="))
    print(title)
    if subtitle:
        print(subtitle)
    print(rule("="))


def section(title: str) -> None:
    print()
    print(title)
    print(rule("-"))


def status_line(label: str, status: str, detail: str = "") -> None:
    left = f"[{status}] {label}"
    if detail:
        print(f"{left:<34} {detail}")
    else:
        print(left)


def kv(label: str, value: object) -> None:
    print(f"{label:<18} {value}")


def prompt(default: str, label: str) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def prompt_int(default: int, label: str) -> int:
    while True:
        raw = prompt(str(default), label)
        try:
            return int(raw)
        except ValueError:
            print("Enter a number.")


def prompt_yes_no(default: bool, label: str) -> bool:
    marker = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{marker}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Enter y or n.")


def choose(label: str, options: Sequence[str], *, default_index: int = 0) -> int:
    if not options:
        raise ValueError("No options to choose from.")
    for idx, option in enumerate(options, start=1):
        marker = "*" if idx - 1 == default_index else " "
        print(f"{marker} {idx}. {option}")
    while True:
        raw = input(f"{label} [{default_index + 1}]: ").strip()
        if not raw:
            return default_index
        try:
            value = int(raw)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= value <= len(options):
            return value - 1
        print(f"Choose 1-{len(options)}.")


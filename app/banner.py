# app/banner.py
from time import sleep
import shutil
import re

# --- color constants ---
END = "\033[0m"
LIGHT_BLUE = 117                     # 256-color light blue
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# ---------- helpers ----------
def _color(s: str) -> str:
    """Wrap a whole string in a single light-blue ANSI color."""
    return f"\033[38;5;{LIGHT_BLUE}m{s}{END}"

def _visible_len(s: str) -> int:
    """Length without ANSI codes."""
    return len(ANSI_RE.sub("", s))

def _leading_spaces_visible(s: str) -> int:
    """Count visible leading spaces (ANSI stripped)."""
    vis = ANSI_RE.sub("", s)
    return len(vis) - len(vis.lstrip(" "))

def haxor_print(text: str, center_to: str | None = None, tick: float = 0.05):
    """
    Animated print that **centers itself under a given banner row**.

    Pass the exact banner row you printed (including ANSI color) as `center_to`.
    This function strips ANSI, measures visible width and leading spaces, and
    computes the pad so the subtitle appears directly beneath the banner.
    """
    if center_to:
        total = _visible_len(center_to)
        lead = _leading_spaces_visible(center_to)
        inner = max(0, total - lead)
        pad = lead + max(0, (inner - len(text)) // 2)
    else:
        pad = 0

    current, mutated = "", ""
    for ch in text:
        current += ch
        mutated += f"\033[1;38;5;{LIGHT_BLUE}m{ch.upper()}{END}"
        print(f'\r{" " * pad}{mutated}', end="")
        sleep(tick)
        print(f'\r{" " * pad}{current}', end="")
        mutated = current
    print(f'\r{" " * pad}{text}\n')

# ---------- banner ----------
def print_banner():
    """
    Renders 'N0b0dy' using your custom glyphs, normalizes glyph widths,
    centers the banner to the terminal, then prints 'Unleashed' **centered
    directly underneath** via haxor_print(center_to=<middle banner row>).
    """

    # --- your edited glyphs (3 rows each) ---
    N = ["┌┐┌ ", "│││ ", "┘└┘ "]
    ZERO = ["┌─┐", "│ │", "└─┘"]
    b = ["│", "│─┐", "└─┘"]
    d = ["  │", "┌─│", "└─┘"]
    y = ["┌ ┐", "└┐│", " └┘"]

    glyphs = [N, ZERO, b, ZERO, d, y]

    # --- normalize: make every glyph row the same width ---
    global_width = max(len(row) for g in glyphs for row in g)
    norm = [[row.ljust(global_width) for row in g] for g in glyphs]

    # build uncolored rows with a single space between glyphs
    sep = " "
    rows_plain = []
    for r in range(3):
        parts = []
        for i, g in enumerate(norm):
            parts.append(g[r])
            if i < len(norm) - 1:
                parts.append(sep)
        rows_plain.append("".join(parts))

    # center the banner to the terminal once
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    banner_width = len(rows_plain[0])
    pad = max(0, (cols - banner_width) // 2)
    pad_str = " " * pad

    # colorize each row and print with identical left padding
    line0 = pad_str + _color(rows_plain[0])
    line1 = pad_str + _color(rows_plain[1])  # use this as centering reference
    line2 = pad_str + _color(rows_plain[2])

    print("\r")
    print(line0)
    print(line1)
    print(line2)

    # subtitle centered **under the banner** using the printed middle row
    haxor_print("Bogush", center_to=line1)

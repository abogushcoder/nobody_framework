# app/state.py
from dataclasses import dataclass

@dataclass
class AppState:
    current_mode: str = "global"
    github_token: str | None = None
    github_username: str | None = None
    github_poll_interval_ms: int = 5000
    # NEW (optional): if provided via -i file, use it; otherwise None
    github_repo_name: str | None = None

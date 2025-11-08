from typing import Optional
from ..state import AppState

import base64
import json
import time
import requests
import os

MASK = "********"

# Adjust as needed
REPO_NAME = "testrepo"
FILE_PATH = "README.md"
BRANCH = "main"          # be explicit
POLL_INTERVAL = 0.5      # seconds

def _clear():
    os.system("cls" if os.name == "nt" else "clear")

def _mask(token: Optional[str]) -> str:
    if not token:
        return "(not set)"
    return token[:4] + MASK + token[-4:] if len(token) > 8 else MASK

def _print_github_help():
    print("GitHub shell commands:")
    print("  help              show this help")
    print("  clear             clear the screen")
    print("  interval [ms]     show or set polling interval in milliseconds")
    print("  token <value>     set token for this session only")
    print("  token             show masked token")
    print("  token --clear     clear token")
    print("  username <value>  set GitHub username")
    print("  username          show current username")
    print("  username --clear  clear username")
    print("  repo [name|--clear] show/set/clear repository name for this run")
    print("  rate              show API remaining requests and reset time")
    print("  connect           enter connect shell to edit README.md live")
    print("  back              return to main prompt")
    print("  exit              return to main prompt")

def enter(state: AppState) -> None:
    _print_github_help()

def handle_line(state: AppState, line: str) -> Optional[str]:
    if not line:
        return None

    if line == "help":
        _print_github_help()
        return None

    if line == "clear":
        _clear()
        return None

    if line in ("back", "exit"):
        state.current_mode = "global"
        return "Returning to main prompt."

        # interval commands
    if line.startswith("interval"):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            return f"Current polling interval: {state.github_poll_interval_ms} ms"
        arg = parts[1].strip()
        if not arg.isdigit():
            return "Interval must be a positive integer (milliseconds)."
        ms = int(arg)
        if ms < 100:
            return "Interval too short; must be >= 100 ms."
        state.github_poll_interval_ms = ms
        return f"Polling interval set to {ms} ms."


    # token commands
    if line.startswith("token"):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            return f"Current token: {_mask(state.github_token)}"
        arg = parts[1].strip()
        if arg == "--clear":
            state.github_token = None
            return "GitHub token cleared for this run."
        state.github_token = arg
        return "GitHub token set for this run."

    # username commands
    if line.startswith("username"):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            current = state.github_username or "(not set)"
            return f"Current GitHub username: {current}"
        arg = parts[1].strip()
        if arg == "--clear":
            state.github_username = None
            return "GitHub username cleared for this run."
        state.github_username = arg
        return f"GitHub username set to '{arg}' for this run."

        # repo commands
    if line.startswith("repo"):
        parts = line.split(maxsplit=1)
        if len(parts) == 1:
            current = state.github_repo_name or REPO_NAME
            return f"Current repo name: {current}"
        arg = parts[1].strip()
        if arg == "--clear":
            state.github_repo_name = None
            return "GitHub repo name cleared for this run."
        state.github_repo_name = arg
        return f"GitHub repo name set to '{arg}' for this run."

    # rate limit info
    if line.strip() == "rate":
        return _rate_limit_info(state)

    # connect command
    if line == "connect":
        return _connect_shell(state)

    return "unrecognized in github shell"






# ----------------------------
# Rate limit helper
# ----------------------------

def _rate_limit_info(state: AppState) -> str:
    if not state.github_token:
        return "GitHub token is not set. Use 'token <value>' first."
    try:
        r = requests.get(
            "https://api.github.com/rate_limit",
            headers={
                "Authorization": f"token {state.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "MyShell/1.0",
            },
            timeout=10,
        )
        # Even on 403 rate-limited responses, headers include limit data
        reset_ts = int(r.headers.get("X-RateLimit-Reset", "0") or 0)
        remaining = r.headers.get("X-RateLimit-Remaining", "?")
        limit = r.headers.get("X-RateLimit-Limit", "?")
        when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset_ts)) if reset_ts else "unknown"
        return f"Remaining: {remaining} / {limit}\nResets at: {when}"
    except requests.RequestException as e:
        return f"Failed to query rate limit: {e}"


# ----------------------------
# Connect-shell (blocking wait)
# ----------------------------

def _api_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MyShell/1.0"
    }

def _contents_url(username: str, repo: str, path: str) -> str:
    return f"https://api.github.com/repos/{username}/{repo}/contents/{path}"

def _get_item(username: str, repo: str, path: str, token: str) -> dict:
    url = _contents_url(username, repo, path)
    r = requests.get(url, headers=_api_headers(token), params={"ref": BRANCH})
    r.raise_for_status()
    return r.json()

def _put_item(username: str, repo: str, path: str, token: str, new_text: str, sha: str) -> requests.Response:
    url = _contents_url(username, repo, path)
    b64_content = base64.b64encode(new_text.encode()).decode()
    payload = {
        "message": f"Update {path} via connect shell",
        "content": b64_content,
        "sha": sha,
        "branch": BRANCH
    }
    return requests.put(url, headers=_api_headers(token), json=payload)


def _get_raw_text(username: str, repo: str, path: str, token: str, ref: str = BRANCH) -> str:
    url = _contents_url(username, repo, path)
    # Ask for raw content directly; this avoids truncation limits
    r = requests.get(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "MyShell/1.0",
    }, params={"ref": ref})
    r.raise_for_status()
    # When Accept: raw, GitHub returns text bytes directly
    return r.text


def _decode_base64_content(item: dict) -> str:
    # If GitHub says content is truncated, bail out to raw fetch in caller
    if item.get("truncated"):
        # Caller should fetch raw; keep this function simple
        raise ValueError("Content truncated; use raw fetch")
    content_b64 = item.get("content", "") or ""
    # GitHub may insert newlines in base64; decoder handles them
    return base64.b64decode(content_b64.encode()).decode(errors="replace")



def _wait_for_change(state, username, repo, path, token, baseline_sha):
    """Poll GitHub until the file's SHA changes or timeout expires."""
    interval = getattr(state, "github_poll_interval_ms", 5000) / 1000.0
    timeout = interval + 5  # timeout = poll interval + 5 seconds
    deadline = time.time() + timeout

    while time.time() < deadline:
        time.sleep(interval)
        try:
            item = _get_item(username, repo, path, token)
            new_sha = item.get("sha")
            if new_sha and new_sha != baseline_sha:
                return item  # success
        except Exception:
            pass  # transient network errors can be ignored briefly

    # Timeout reached — return None to indicate no change
    return None


def _connect_help():
    print("connect shell commands:")
    print("  help or :help   show this help")
    print("  :show           print the current file content")
    print("  :back           return to github shell")
    print("  <any text>      overwrite README.md with that text and block until change is observed")

def _connect_shell(state: AppState) -> str:
    if not state.github_username:
        return "GitHub username is not set. Use 'username <value>' first."
    if not state.github_token:
        return "GitHub token is not set. Use 'token <value>' first."

    username = state.github_username
    token = state.github_token
    repo = state.github_repo_name
    path = FILE_PATH

    try:
        item = _get_item(username, repo, path, token)
    except requests.HTTPError as e:
        return f"Failed to read {path}: {e.response.status_code} {e.response.text}"
    except requests.RequestException as e:
        return f"Network error: {e}"

    print(f"Connected to {username}/{repo}:{path} on branch '{BRANCH}'.")
    print("Type text to overwrite README.md, or type 'help' for commands.")
    _connect_help()

    while True:
        try:
            line = input("connect> ").rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            print()
            return "Returning to github shell."

        if not line:
            continue

        if line in (":help", "help"):
            _connect_help()
            continue

        # IMPORTANT: clear is disabled in connect shell
        if line == "clear":
            print("clear is disabled in connect shell.")
            continue

        if line == ":back":
            return "Returning to github shell."

        if line == ":show":
            try:
                item = _get_item(username, repo, path, token)
                print(_decode_base64_content(item))
            except requests.RequestException as e:
                print(f"Failed to read: {e}")
            continue

        # write then block until change is visible
        try:
            item_before = _get_item(username, repo, path, token)
            baseline_sha = item_before.get("sha")

            resp = _put_item(username, repo, path, token, line, baseline_sha)
            if resp.status_code not in (200, 201):
                print(f"Failed to update: {resp.status_code}")
                try:
                    print(resp.json())
                except Exception:
                    print(resp.text)
                continue

            try:
                posted_sha = resp.json().get("content", {}).get("sha") or baseline_sha
            except Exception:
                posted_sha = baseline_sha

            # Wait until SHA changes
            observed_baseline = posted_sha if posted_sha != baseline_sha else baseline_sha
            item_after = _wait_for_change(state, username, repo, path, token, observed_baseline)

            # Instead of decoding JSON 'content' (which may be truncated),
            # fetch the full raw file and print it.
            try:
                full_text = _get_raw_text(username, repo, path, token, ref=BRANCH)
            except requests.RequestException as e:
                # Fallback to JSON decoding if raw fetch ever fails
                try:
                    full_text = _decode_base64_content(item_after)
                except Exception:
                    full_text = "<failed to fetch updated content>"

            print("[README.md changed]")
            print(full_text)

        except requests.RequestException as e:
            print(f"Failed to update: {e}")
            # loop continues

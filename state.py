from typing import Dict
from datetime import datetime
import threading
from models import Message, Group, ClientSession

# --- Global state ---
# username -> ClientSession
clients: Dict[str, ClientSession] = {}

# groupName -> Group
groups: Dict[str, Group] = {}

# Global message id counter (shared across all groups)
_next_msg_id: int = 1

# Single mutex for all shared state. Good enough for this project.
state_lock = threading.Lock()


# --- Small helpers ---

def log(msg: str) -> None:
    """Tiny logger so I can grep server output easily."""
    print(f"[SERVER] {msg}")


def allocate_message_id() -> int:
    """
    Grab the next message id.

    NOTE: this must be called while holding `state_lock`.
    """
    global _next_msg_id
    msg_id = _next_msg_id
    _next_msg_id += 1
    return msg_id


def send_line(session: ClientSession, line: str) -> None:
    """
    Fire-and-forget send. If it blows up, we just log and move on.
    """
    try:
        session.writer.write(line + "\n")
        session.writer.flush()
    except Exception as e:
        log(f"Failed to send to {session.username}: {e}")


def send_ok(session: ClientSession, code: str, detail: str = "") -> None:
    """
    Convenience wrapper: OK + code + optional detail.
    """
    if detail:
        send_line(session, f"OK {code} {detail}")
    else:
        send_line(session, f"OK {code}")


def send_err(session: ClientSession, code: str, detail: str = "") -> None:
    """
    Convenience wrapper: ERR + code + optional detail.
    """
    if detail:
        send_line(session, f"ERR {code} {detail}")
    else:
        send_line(session, f"ERR {code}")


def broadcast_event(group_name: str, payload: str, exclude_username: str | None = None) -> None:
    """
    Broadcast an EVENT line to all members of a group.

    `payload` is everything after the `EVENT ` prefix.
    """
    with state_lock:
        group = groups.get(group_name)
        if not group:
            return

        # Snapshot the current sessions so we don't hold the lock while writing.
        recipients = [
            clients[u]
            for u in group.members
            if u in clients and u != exclude_username
        ]

    for sess in recipients:
        send_line(sess, f"EVENT {payload}")

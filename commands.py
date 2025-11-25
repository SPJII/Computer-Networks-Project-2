from datetime import datetime
from models import ClientSession, Message
from state import (
    state_lock,
    groups,
    clients,
    log,
    allocate_message_id,
    send_line,
    send_ok,
    send_err,
    broadcast_event,
)

# --- Small local helpers ---


def parse_subject_body(payload: str):
    """
    Parse 'subject|body'.

    Returns (subject, body) or (None, None) if the format is bad.

    Subject cannot be empty; body can be empty.
    """
    if "|" not in payload:
        return None, None
    subject, body = payload.split("|", 1)
    subject = subject.strip()
    body = body.strip()
    if not subject:
        return None, None
    return subject, body


# --- Individual commands ---

def cmd_ping(session: ClientSession) -> None:
    """PING -> PONG; trivial liveness check."""
    send_ok(session, "PONG")


def cmd_groups(session: ClientSession) -> None:
    """GROUPS -> list of group names."""
    with state_lock:
        all_groups = ",".join(sorted(groups.keys()))
    send_ok(session, "GROUP_LIST", all_groups)


def cmd_join(session: ClientSession, group_name: str) -> None:
    """
    JOIN <groupName>

    - Group must exist (we pre-create them in server.main()).
    - If you're already in, we just tell you that.
    """
    group_name = group_name.strip()
    if not group_name:
        send_err(session, "BAD_ARGS", "JOIN requires a group name")
        return

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return

        if session.username in group.members:
            already = True
        else:
            group.members.add(session.username)
            session.groups.add(group_name)
            already = False

    if already:
        send_ok(session, "ALREADY_IN_GROUP", group_name)
    else:
        send_ok(session, "JOINED", group_name)
        broadcast_event(group_name, f"USER_JOINED {group_name} {session.username}",
                        exclude_username=session.username)


def cmd_leave(session: ClientSession, group_name: str) -> None:
    """
    LEAVE <groupName>

    Just drops you from the group's member set.
    """
    group_name = group_name.strip()
    if not group_name:
        send_err(session, "BAD_ARGS", "LEAVE requires a group name")
        return

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return

        if session.username not in group.members:
            send_err(session, "NOT_IN_GROUP", group_name)
            return

        group.members.remove(session.username)
        session.groups.discard(group_name)

    send_ok(session, "LEFT", group_name)
    broadcast_event(group_name, f"USER_LEFT {group_name} {session.username}",
                    exclude_username=session.username)


def cmd_who(session: ClientSession, group_name: str) -> None:
    """
    WHO <groupName>

    Returns comma-separated list of users in that group.
    """
    group_name = group_name.strip()
    if not group_name:
        send_err(session, "BAD_ARGS", "WHO requires a group name")
        return

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return
        members = ",".join(sorted(group.members))

    # Format: OK GROUP_USERS <groupName> user1,user2,...
    send_ok(session, "GROUP_USERS", f"{group_name} {members}")


def cmd_post(session: ClientSession, group_name: str, payload: str) -> None:
    """
    POST <groupName> <subject>|<body>

    - Requires that the group exists and the user is a member.
    - Broadcasts an EVENT MESSAGE line to everyone in the group.
    """
    group_name = group_name.strip()
    if not group_name:
        send_err(session, "BAD_ARGS",
                 "POST requires a group name and subject|body")
        return

    subject, body = parse_subject_body(payload)
    if subject is None:
        send_err(session, "BAD_ARGS", "POST payload must be 'subject|body'")
        return

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return

        if session.username not in group.members:
            send_err(session, "NOT_IN_GROUP", group_name)
            return

        msg_id = allocate_message_id()
        msg = Message(
            msg_id=msg_id,
            sender=session.username,
            subject=subject,
            body=body,
            timestamp=datetime.utcnow(),
        )
        group.messages.append(msg)

        summary = (
            f"MESSAGE {group_name} "
            f"{msg.msg_id}|{msg.sender}|{msg.timestamp.isoformat()}|{msg.subject}"
        )

    # Do the broadcast outside the lock.
    broadcast_event(group_name, summary)
    send_ok(session, "POSTED", f"{group_name} {msg_id}")


def cmd_get(session: ClientSession, group_name: str, msg_id_str: str) -> None:
    """
    GET <groupName> <msgId>

    Returns one OK MESSAGE ... line with full content if found.
    """
    group_name = group_name.strip()
    msg_id_str = msg_id_str.strip()

    if not group_name or not msg_id_str:
        send_err(session, "BAD_ARGS", "GET requires group name and message id")
        return

    if not msg_id_str.isdigit():
        send_err(session, "BAD_MESSAGE_ID", msg_id_str)
        return

    msg_id = int(msg_id_str)

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return
        if session.username not in group.members:
            send_err(session, "NOT_IN_GROUP", group_name)
            return

        msg = next((m for m in group.messages if m.msg_id == msg_id), None)

    if not msg:
        send_err(session, "MESSAGE_NOT_FOUND", f"{group_name}:{msg_id}")
        return

    payload = (
        f"{group_name} "
        f"{msg.msg_id}|{msg.sender}|{msg.timestamp.isoformat()}|{msg.subject}|{msg.body}"
    )
    send_ok(session, "MESSAGE", payload)


def cmd_history(session: ClientSession, group_name: str, n_str: str) -> None:
    """
    HISTORY <groupName> <N>

    Emits EVENT HISTORY lines followed by OK HISTORY_END <groupName>.
    """
    group_name = group_name.strip()
    n_str = n_str.strip()

    if not group_name or not n_str:
        send_err(session, "BAD_ARGS", "HISTORY requires group name and N")
        return

    if not n_str.isdigit():
        send_err(session, "BAD_HISTORY_COUNT", n_str)
        return

    n = int(n_str)
    if n <= 0:
        send_err(session, "BAD_HISTORY_COUNT", "N must be > 0")
        return

    with state_lock:
        group = groups.get(group_name)
        if not group:
            send_err(session, "UNKNOWN_GROUP", group_name)
            return
        if session.username not in group.members:
            send_err(session, "NOT_IN_GROUP", group_name)
            return

        last_msgs = group.messages[-n:]

    for msg in last_msgs:
        line = (
            f"HISTORY {group_name} "
            f"{msg.msg_id}|{msg.sender}|{msg.timestamp.isoformat()}|{msg.subject}"
        )
        send_line(session, f"EVENT {line}")

    send_ok(session, "HISTORY_END", group_name)

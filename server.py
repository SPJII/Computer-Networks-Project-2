import socket
import threading
from typing import Optional
from models import ClientSession, Group
from state import (
    log,
    state_lock,
    groups,
    clients,
    send_ok,
    send_err,
    broadcast_event,
)
from commands import (
    cmd_ping,
    cmd_groups,
    cmd_join,
    cmd_leave,
    cmd_who,
    cmd_post,
    cmd_get,
    cmd_history,
)


def handle_client(sock: socket.socket, addr) -> None:
    """
    One thread per client. Handles:
    - USER handshake
    - Auto-join of 'lobby'
    - Initial lobby history / user list
    - Command routing loop
    - Cleanup on disconnect
    """
    log(f"Incoming connection from {addr}")

    rfile = sock.makefile("r", encoding="utf-8", newline="\n")
    wfile = sock.makefile("w", encoding="utf-8", newline="\n")

    session: Optional[ClientSession] = None

    try:
        # USER handshake
        wfile.write("OK WELCOME Use: USER <username>\n")
        wfile.flush()

        while session is None:
            raw = rfile.readline()
            if not raw:
                log(f"{addr} disconnected before USER")
                return

            line = raw.strip()
            if not line:
                continue

            parts = line.split(" ", 1)
            cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if cmd != "USER":
                wfile.write("ERR FIRST_COMMAND_MUST_BE_USER\n")
                wfile.flush()
                continue

            username = args.strip()
            if not username:
                wfile.write("ERR USERNAME_REQUIRED\n")
                wfile.flush()
                continue

            with state_lock:
                if username in clients:
                    wfile.write("ERR USERNAME_IN_USE\n")
                    wfile.flush()
                    continue

                # create session
                session = ClientSession(username=username, sock=sock, writer=wfile)
                clients[username] = session

                # auto-join lobby
                lobby = groups.get("lobby")
                if lobby:
                    lobby.members.add(username)
                    session.groups.add("lobby")

                # snapshot last 2 lobby messages & current lobby users
                last_two = lobby.messages[-2:] if lobby else []
                lobby_users = sorted(lobby.members) if lobby else []

            log(f"User '{username}' logged in from {addr}")

            # ack + initial history + lobby members
            send_ok(session, "USER_ACCEPTED", username)

            for msg in last_two:
                history_line = (
                    f"HISTORY lobby "
                    f"{msg.msg_id}|{msg.sender}|{msg.timestamp.isoformat()}|{msg.subject}"
                )
                # important: this is an EVENT, not an OK
                from state import send_line  # local import to avoid clutter at top
                send_line(session, f"EVENT {history_line}")

            send_ok(session, "LOBBY_USERS", ",".join(lobby_users))

            # tell everyone else in lobby we joined
            broadcast_event("lobby", f"USER_JOINED lobby {username}",
                            exclude_username=username)

        # Main command loop
        while True:
            raw = rfile.readline()
            if not raw:
                # client hung up
                break

            line = raw.strip()
            if not line:
                continue

            parts = line.split(" ", 2)
            cmd = parts[0].upper()
            arg1 = parts[1] if len(parts) > 1 else ""
            arg2 = parts[2] if len(parts) > 2 else ""

            # This is basically a big switch statement.
            if cmd == "PING":
                cmd_ping(session)

            elif cmd == "GROUPS":
                cmd_groups(session)

            elif cmd == "JOIN":
                cmd_join(session, arg1)

            elif cmd == "LEAVE":
                cmd_leave(session, arg1)

            elif cmd == "WHO":
                cmd_who(session, arg1)

            elif cmd == "POST":
                # POST <group> <subject>|<body>
                if not arg1 or not arg2:
                    send_err(session, "BAD_ARGS", "POST <group> <subject>|<body>")
                else:
                    cmd_post(session, arg1, arg2)

            elif cmd == "GET":
                # GET <group> <id>
                if not arg1 or not arg2:
                    send_err(session, "BAD_ARGS", "GET <group> <id>")
                else:
                    cmd_get(session, arg1, arg2)

            elif cmd == "HISTORY":
                # HISTORY <group> <N>
                if not arg1 or not arg2:
                    send_err(session, "BAD_ARGS", "HISTORY <group> <N>")
                else:
                    cmd_history(session, arg1, arg2)

            elif cmd == "QUIT":
                send_ok(session, "BYE")
                break

            else:
                send_err(session, "UNKNOWN_COMMAND", cmd)

    except Exception as e:
        log(f"Exception in client handler {addr}: {e}")

    finally:
        # Cleanup: drop from global state and broadcast USER_LEFT for each group
        if session is not None:
            username = session.username
            log(f"Cleaning up user '{username}'")
            left_groups = []

            with state_lock:
                clients.pop(username, None)
                for gname, g in groups.items():
                    if username in g.members:
                        g.members.remove(username)
                        left_groups.append(gname)

            for gname in left_groups:
                broadcast_event(gname, f"USER_LEFT {gname} {username}",
                                exclude_username=username)

        try:
            sock.close()
        except Exception:
            pass

        log(f"Connection from {addr} closed")


def main() -> None:
    """
    Bootstraps the TCP listener and pre-creates the groups.

    This is also where you'd tweak the port / group names.
    """
    host = "0.0.0.0"
    port = 5000

    # Pre-create the 5 groups (Part 2 requirement).
    initial_groups = ["lobby", "games", "cs", "random", "music"]
    with state_lock:
        for name in initial_groups:
            if name not in groups:
                groups[name] = Group(name=name)

    log(f"Starting server on {host}:{port}")
    log(f"Groups: {', '.join(sorted(groups.keys()))}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen()
        log("Listening for incoming connections...")

        while True:
            client_sock, addr = srv.accept()
            t = threading.Thread(
                target=handle_client,
                args=(client_sock, addr),
                daemon=True, 
            )
            t.start()


if __name__ == "__main__":
    main()

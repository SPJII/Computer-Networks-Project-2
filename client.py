import socket
import threading

SERVER_PORT_DEFAULT = 5055
sock = None
rfile = None
wfile = None
running = True


def receiver_loop():
    """Background thread, prints anything the server sends"""
    global rfile, running
    try:
        while running:
            line = rfile.readline()
            if not line:
                print("** Disconnected from server **")
                running = False
                break
            print(line.rstrip())
    except Exception as e:
        print(f"** Receiver error: {e}")
        running = False


def cmd_connect(host: str, port: int):
    """Connect to the bulletin board server"""
    global sock, rfile, wfile, running
    if sock is not None:
        print("Already connected.")
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        sock = s
        rfile = sock.makefile("r", encoding="utf-8", newline="\n")
        wfile = sock.makefile("w", encoding="utf-8", newline="\n")
        running = True

        t = threading.Thread(target=receiver_loop, daemon=True)
        t.start()

        print(f"Connected to {host}:{port}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sock = None
        rfile = None
        wfile = None


def send_line(line: str):
    """Send a raw line to the server."""
    global wfile
    if wfile is None:
        print("Not connected. Use %connect first.")
        return
    try:
        wfile.write(line + "\n")
        wfile.flush()
    except Exception as e:
        print(f"Send failed: {e}")


def print_help():
    print("Commands:")
    print("  %connect <host> <port>")
    print("  %user <username>")
    print("  %join              (join lobby)")
    print("  %post <subject>|<body>")
    print("  %users             (users in lobby)")
    print("  %message <id>      (get one lobby message)")
    print("  %leave             (leave lobby)")
    print("  %groups")
    print("  %groupjoin <group>")
    print("  %grouppost <group> <subject>|<body>")
    print("  %groupusers <group>")
    print("  %groupleave <group>")
    print("  %groupmessage <group> <id>")
    print("  %history <group> <N>")
    print("  %exit")
    print()


def main():
    global running, sock

    print("Bulletin Board Client")
    print_help()

    while True:
        try:
            line = input("> ").rstrip()
        except EOFError:
            break

        if not line:
            continue

        # client-side commands start with %
        if not line.startswith("%"):
            print("Commands must start with %")
            continue

        # CONNECT
        if line.startswith("%connect "):
            parts = line.split()
            if len(parts) != 3:
                print("Usage: %connect <host> <port>")
                continue
            host = parts[1]
            try:
                port = int(parts[2])
            except ValueError:
                print("Port must be an integer.")
                continue
            cmd_connect(host, port)

        # USER
        elif line.startswith("%user "):
            username = line[len("%user "):].strip()
            if not username:
                print("Usage: %user <username>")
                continue
            send_line(f"USER {username}")

        # LOBBY JOIN
        elif line.strip() == "%join":
            send_line("JOIN lobby")

        # LOBBY POST
        elif line.startswith("%post "):
            payload = line[len("%post "):].strip()
            if "|" not in payload:
                print("Usage: %post <subject>|<body>")
                continue
            send_line(f"POST lobby {payload}")

        # LOBBY USERS
        elif line.strip() == "%users":
            send_line("WHO lobby")

        # LOBBY MESSAGE CONTENT
        elif line.startswith("%message "):
            msg_id = line[len("%message "):].strip()
            if not msg_id:
                print("Usage: %message <id>")
                continue
            send_line(f"GET lobby {msg_id}")

        # LOBBY LEAVE
        elif line.strip() == "%leave":
            send_line("LEAVE lobby")

        # GROUP LIST
        elif line.strip() == "%groups":
            send_line("GROUPS")

        # GROUP JOIN
        elif line.startswith("%groupjoin "):
            group = line[len("%groupjoin "):].strip()
            if not group:
                print("Usage: %groupjoin <group>")
                continue
            send_line(f"JOIN {group}")

        # GROUP POST
        elif line.startswith("%grouppost "):
            # format: %grouppost <group> <subject>|<body>
            parts = line.split(" ", 2)
            if len(parts) < 3:
                print("Usage: %grouppost <group> <subject>|<body>")
                continue
            group = parts[1].strip()
            payload = parts[2].strip()
            if not group or "|" not in payload:
                print("Usage: %grouppost <group> <subject>|<body>")
                continue
            send_line(f"POST {group} {payload}")

        # GROUP USERS
        elif line.startswith("%groupusers "):
            group = line[len("%groupusers "):].strip()
            if not group:
                print("Usage: %groupusers <group>")
                continue
            send_line(f"WHO {group}")

        # GROUP LEAVE
        elif line.startswith("%groupleave "):
            group = line[len("%groupleave "):].strip()
            if not group:
                print("Usage: %groupleave <group>")
                continue
            send_line(f"LEAVE {group}")

        # GROUP MESSAGE CONTENT
        elif line.startswith("%groupmessage "):
            # format: %groupmessage <group> <id>
            parts = line.split()
            if len(parts) != 3:
                print("Usage: %groupmessage <group> <id>")
                continue
            group = parts[1]
            msg_id = parts[2]
            send_line(f"GET {group} {msg_id}")

        # HISTORY
        elif line.startswith("%history "):
            # format: %history <group> <N>
            parts = line.split()
            if len(parts) != 3:
                print("Usage: %history <group> <N>")
                continue
            group = parts[1]
            n = parts[2]
            send_line(f"HISTORY {group} {n}")

        # EXIT
        elif line.strip() == "%exit":
            if sock is not None:
                send_line("QUIT")
            running = False
            break

        # HELP
        elif line.strip() in ("%help", "%h"):
            print_help()

        else:
            print("Unknown client command. Use %help for a list.")

    # cleanup
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass
    print("Client exiting.")


if __name__ == "__main__":
    main()

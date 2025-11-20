# Multi-Group Bulletin Board Server – Protocol & Client Guide

This repo contains the **server** for our TCP bulletin board project.  

This document explains:
- how to run the server
- how the wire protocol works
- what commands your client can send
- what responses and events to expect

## 1. Running the Server

### Requirements

- Python 3.10+ (3.8+ will probably work, but I’ve been using 3.10+)
- No external dependencies — just the standard library

### Folder layout

The server code is split up for readability:

- `models.py` – dataclasses for `Message`, `Group`, `ClientSession`
- `state.py` – global state, locks, logging, send helpers
- `commands.py` – protocol command handlers (POST, GET, etc.)
- `server.py` – TCP listener, per-client handler, command routing

### Start the server

From inside the repo directory run server.py

### How it works
The server speaks a simple text protocol over TCP:

One UTF-8 line per command/response, terminated by \n.

The client connects, then the first real command must be:
USER <username>

After a successful USER, the user is auto-joined into the lobby group and can start sending commands.

The server can send two kinds of lines:

Synchronous replies that start with OK or ERR

Asynchronous events that start with EVENT
(e.g. other users joining, new messages)

### What commands your client can send

All commands are sent as plain text lines:

USER <username> – login / register your username (must be unique; first command).

PING – health check; server replies with OK PONG.

GROUPS – get a list of all group names.

JOIN <groupName> – join a group (user must do this before posting there, except lobby, which is auto-joined).

LEAVE <groupName> – leave a group but stay connected.

WHO <groupName> – list users currently in that group.

POST <groupName> <subject>|<body> – post a message to a group.

GET <groupName> <messageId> – fetch full message content (subject + body).

HISTORY <groupName> <N> – fetch up to N recent messages (summary only) for that group.

QUIT – graceful disconnect; server responds and then closes the connection.

### What responses and events to expect

# (1)
### OK responses (success)

OK <CODE> [extra data...]

# Examples:
OK WELCOME Use: USER <username> (initial greeting)

OK USER_ACCEPTED alice

OK GROUP_LIST lobby,games,cs,random,music

OK POSTED cs 7

OK MESSAGE cs 7|alice|<isoTime>|Subject|Body

OK LOBBY_USERS user1,user2

OK HISTORY_END cs

OK BYE (after QUIT)

# (2)
### ERR responses (errors)

ERR <CODE> [optional detail]

# Examples:
ERR FIRST_COMMAND_MUST_BE_USER

ERR USERNAME_REQUIRED

ERR USERNAME_IN_USE

ERR UNKNOWN_GROUP cs2

ERR NOT_IN_GROUP cs

ERR BAD_ARGS POST requires a group name and subject|body

ERR BAD_MESSAGE_ID 999
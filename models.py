from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Set, Any
import socket


@dataclass
class Message:
    """
    Represents a single message posted to a group.
    """
    msg_id: int
    sender: str
    subject: str
    body: str
    timestamp: datetime


@dataclass
class Group:
    """
    A single "board" / group.
    """
    name: str
    messages: List[Message] = field(default_factory=list)
    members: Set[str] = field(default_factory=set)


@dataclass
class ClientSession:
    """
    Per-connection state, kept only in memory.

    When the socket dies, this object should be cleaned up from global state.
    """
    username: str
    sock: socket.socket
    writer: Any  # text-mode file wrapper (makefile("w"))
    groups: Set[str] = field(default_factory=set)

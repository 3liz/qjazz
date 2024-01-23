
from dataclasses import dataclass, field
from enum import Enum, auto

from typing_extensions import (
    Any,
    ClassVar,
    Dict,
)

@dataclass(frozen=True)
class Envelop:
    status: int
    msg: Optional[Any]


def send_reply(conn, msg: Optional[Any], status: int = 200):
    """  Send a reply in a envelope message
    """
    conn.send(Envelop(status, msg))


class MsgType(Enum):
    RUN_PROCESS = auto()


@dataclass(frozen=True)
class ProcessResponse:
    outputs: Dict[str, Output]


@dataclass(frozen=True)
class RunProcess:
    msg_id: ClassVar[MsgType] = MsgType.RUN_PROCESS
    return_type: ClassVar[Type] = ProcessResponse
    name: str
    target: Optional[str] = None
    inputs: Dict[str, Input]


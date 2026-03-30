from enum import StrEnum


class ChangeFlag(StrEnum):
    CREATE = "create"
    MOUNTS = "mounts"
    FORWARDS = "forwards"
    EXECS = "execs"
    SETUP = "setup"


ALL_FLAGS = frozenset(ChangeFlag)


class Capability(StrEnum):
    PEERS = "peers"
    MESH = "mesh"
    EXECS = "execs"

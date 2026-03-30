from typing import Literal

from pydantic import BaseModel, Field, computed_field

from jailrun.schemas.base import (
    BaseForwardConfig,
    BaseMountConfig,
    ExecConfig,
    JailBaseConfig,
    JailForwardConfig,
    JailMountConfig,
    SetupStep,
    private_jail_name,
)


class JailState(BaseModel):
    name: str
    base: JailBaseConfig | None = None
    release: str
    ip: str | None = None
    forwards: dict[str, JailForwardConfig] = Field(default_factory=dict)
    mounts: dict[str, JailMountConfig] = Field(default_factory=dict)
    execs: dict[str, ExecConfig] = Field(default_factory=dict)
    setup: dict[str, SetupStep] = Field(default_factory=dict)

    @computed_field
    def private_name(self) -> str:
        return private_jail_name(self.name)


class BaseState(BaseModel):
    setup: dict[str, SetupStep] = Field(default_factory=dict)
    forwards: dict[str, BaseForwardConfig] = Field(default_factory=dict)
    mounts: dict[str, BaseMountConfig] = Field(default_factory=dict)


class QemuFwd(BaseModel):
    proto: Literal["tcp", "udp"]
    host: int
    guest: int


class QemuShare(BaseModel):
    host: str
    id: str
    mount_tag: str


class PeerJail(BaseModel):
    name: str
    ygg_address: str


class PeerState(BaseModel):
    alias: str
    direction: Literal["init", "joined"]
    paired_at: str
    jails: list[PeerJail] = Field(default_factory=list)


class State(BaseModel):
    version: int = 1
    base: BaseState = Field(default_factory=BaseState)
    jails: dict[str, JailState] = Field(default_factory=dict)
    launched_fwds: list[QemuFwd] = Field(default_factory=list)
    launched_shares: list[QemuShare] = Field(default_factory=list)
    ssh_port: int | None = None
    peers: list[PeerState] = Field(default_factory=list)

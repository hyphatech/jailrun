import hashlib
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator


def private_jail_name(name: str) -> str:
    return "j" + hashlib.sha256(name.encode()).hexdigest()[:12]


class HealthcheckConfig(BaseModel):
    test: str
    interval: str = "30s"
    timeout: str = "10s"
    retries: int = 3

    @computed_field
    def timeout_seconds(self) -> int:
        return self._parse_seconds(self.timeout)

    @computed_field
    def interval_cycles(self) -> int:
        secs = self._parse_seconds(self.interval)
        return max(1, secs // 30)

    @staticmethod
    def _parse_seconds(val: str) -> int:
        val = val.strip().lower()
        for suffix, mult in [("ms", 0.001), ("s", 1), ("m", 60), ("h", 3600)]:
            if val.endswith(suffix):
                return max(1, int(float(val[: -len(suffix)]) * mult))
        return int(float(val))


class ExecConfig(BaseModel):
    cmd: str
    dir: str = "/"
    env: dict[str, str] = Field(default_factory=dict)
    healthcheck: HealthcheckConfig | None = None


class LocalSetupStep(BaseModel):
    type: Literal["ansible"] = "ansible"
    file: str
    vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("file")
    @classmethod
    def file_must_not_be_url(cls, v: str) -> str:
        if v.startswith(("https://", "http://")):
            raise ValueError(f"'{v}' looks like a URL — use 'url' instead of 'file'")
        return v


class RemoteSetupStep(BaseModel):
    type: Literal["ansible"] = "ansible"
    url: str
    vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def url_must_be_url(cls, v: str) -> str:
        if not v.startswith(("https://", "http://", "hub://")):
            raise ValueError(f"'{v}' looks like a path — use 'file' instead of 'url'")
        return v


SetupStep = LocalSetupStep | RemoteSetupStep


class BaseForwardConfig(BaseModel):
    proto: Literal["tcp", "udp"] = "tcp"
    host: int
    target: int


class BaseMountConfig(BaseModel):
    host: str
    target: str


class BaseConfig(BaseModel):
    setup: dict[str, SetupStep] = Field(default_factory=dict)
    forward: dict[str, BaseForwardConfig] = Field(default_factory=dict)
    mount: dict[str, BaseMountConfig] = Field(default_factory=dict)


class JailForwardConfig(BaseModel):
    proto: Literal["tcp", "udp"] = "tcp"
    host: int
    jail: int


class JailMountConfig(BaseModel):
    host: str
    jail: str


class JailBaseConfig(BaseModel):
    type: Literal["jail"] = "jail"
    name: str

    @computed_field
    def private_name(self) -> str:
        return private_jail_name(self.name)


class JailConfig(BaseModel):
    name: str
    release: str | None = None
    ip: str | None = None
    base: JailBaseConfig | None = None
    depends: list[str] = Field(default_factory=list)
    forward: dict[str, JailForwardConfig] = Field(default_factory=dict)
    mount: dict[str, JailMountConfig] = Field(default_factory=dict)
    setup: dict[str, SetupStep] = Field(default_factory=dict)
    exec: dict[str, ExecConfig] = Field(default_factory=dict)

    @computed_field
    def private_name(self) -> str:
        return private_jail_name(self.name)


class Config(BaseModel):
    base: BaseConfig | None = None
    jail: dict[str, JailConfig] = Field(default_factory=dict)


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

    def is_empty(self) -> bool:
        return not any([self.setup, self.forwards, self.mounts])


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


class JailPlan(BaseModel):
    name: str
    release: str
    ip: str | None = None
    base: JailBaseConfig | None = None

    @computed_field
    def private_name(self) -> str:
        return private_jail_name(self.name)


class MountPlan(BaseModel):
    mount_tag: str
    target: str


class ExecPlan(BaseModel):
    name: str
    jail: str
    cmd: str
    dir: str = "/"
    env: dict[str, str] = Field(default_factory=dict)
    healthcheck: HealthcheckConfig | None = None

    @computed_field
    def jail_private_name(self) -> str:
        return private_jail_name(self.jail)


class RdrPlan(BaseModel):
    jail: str
    proto: Literal["tcp", "udp"] = "tcp"
    target_port: int
    jail_port: int

    @computed_field
    def jail_private_name(self) -> str:
        return private_jail_name(self.jail)


class NullfsPlan(BaseModel):
    jail: str
    target_path: str
    jail_path: str

    @computed_field
    def jail_private_name(self) -> str:
        return private_jail_name(self.jail)


class StaleMountPlan(BaseModel):
    mount_tag: str
    target: str


class StaleNullfsPlan(BaseModel):
    jail: str
    target_path: str

    @computed_field
    def jail_private_name(self) -> str:
        return private_jail_name(self.jail)


class StaleJailPlan(BaseModel):
    name: str

    @computed_field
    def private_name(self) -> str:
        return private_jail_name(self.name)


class Plan(BaseModel):
    jails: list[JailPlan] = Field(default_factory=list)
    mounts: list[MountPlan] = Field(default_factory=list)
    execs: list[ExecPlan] = Field(default_factory=list)
    jail_rdrs: list[RdrPlan] = Field(default_factory=list)
    jail_mounts: list[NullfsPlan] = Field(default_factory=list)
    stale_jails: list[StaleJailPlan] = Field(default_factory=list)
    stale_mounts: list[StaleMountPlan] = Field(default_factory=list)
    stale_jail_mounts: list[StaleNullfsPlan] = Field(default_factory=list)

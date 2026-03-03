from typing import Literal

from pydantic import BaseModel, Field, computed_field


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
    healthcheck: HealthcheckConfig | None = None


class SetupStep(BaseModel):
    type: Literal["ansible"] = "ansible"
    file: str


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


class JailConfig(BaseModel):
    release: str | None = None
    ip: str | None = None
    base: JailBaseConfig | None = None
    depends: list[str] = Field(default_factory=list)
    forward: dict[str, JailForwardConfig] = Field(default_factory=dict)
    mount: dict[str, JailMountConfig] = Field(default_factory=dict)
    setup: dict[str, SetupStep] = Field(default_factory=dict)
    exec: dict[str, ExecConfig] = Field(default_factory=dict)


class Config(BaseModel):
    base: BaseConfig | None = None
    jail: dict[str, JailConfig] = Field(default_factory=dict)


class JailState(BaseModel):
    base: JailBaseConfig | None = None
    release: str
    ip: str | None = None
    forwards: dict[str, JailForwardConfig] = Field(default_factory=dict)
    mounts: dict[str, JailMountConfig] = Field(default_factory=dict)
    execs: dict[str, ExecConfig] = Field(default_factory=dict)
    setup: dict[str, SetupStep] = Field(default_factory=dict)


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


class State(BaseModel):
    version: int = 1
    base: BaseState = Field(default_factory=BaseState)
    jails: dict[str, JailState] = Field(default_factory=dict)
    launched_fwds: list[QemuFwd] = Field(default_factory=list)
    launched_shares: list[QemuShare] = Field(default_factory=list)


class JailPlan(BaseModel):
    name: str
    release: str
    ip: str | None = None
    base: JailBaseConfig | None = None


class MountPlan(BaseModel):
    mount_tag: str
    target: str


class ExecPlan(BaseModel):
    name: str
    jail: str
    cmd: str
    dir: str = "/"
    healthcheck: HealthcheckConfig | None = None


class RdrPlan(BaseModel):
    jail: str
    proto: Literal["tcp", "udp"] = "tcp"
    target_port: int
    jail_port: int


class NullfsPlan(BaseModel):
    jail: str
    target_path: str
    jail_path: str


class StaleMountPlan(BaseModel):
    mount_tag: str
    target: str


class StaleNullfsPlan(BaseModel):
    jail: str
    target_path: str


class Plan(BaseModel):
    jails: list[JailPlan] = Field(default_factory=list)
    mounts: list[MountPlan] = Field(default_factory=list)
    execs: list[ExecPlan] = Field(default_factory=list)
    jail_rdrs: list[RdrPlan] = Field(default_factory=list)
    jail_mounts: list[NullfsPlan] = Field(default_factory=list)
    stale_jails: list[str] = Field(default_factory=list)
    stale_mounts: list[StaleMountPlan] = Field(default_factory=list)
    stale_jail_mounts: list[StaleNullfsPlan] = Field(default_factory=list)

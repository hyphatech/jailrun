from typing import Literal

from pydantic import BaseModel, Field, computed_field

from jailrun.schemas.base import HealthcheckConfig, JailBaseConfig, private_jail_name


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
    jail_path: str

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

    def for_jail(self, name: str) -> "Plan":
        return Plan(
            jails=[j for j in self.jails if j.name == name],
            jail_mounts=[m for m in self.jail_mounts if m.jail == name],
            stale_jail_mounts=[m for m in self.stale_jail_mounts if m.jail == name],
            jail_rdrs=[r for r in self.jail_rdrs if r.jail == name],
            execs=[e for e in self.execs if e.jail == name],
        )

    def for_jails(self, names: set[str]) -> "Plan":
        return Plan(
            jails=[j for j in self.jails if j.name in names],
            jail_rdrs=[r for r in self.jail_rdrs if r.jail in names],
        )

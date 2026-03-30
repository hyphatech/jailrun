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


class BaseConfig(BaseModel):
    setup: dict[str, SetupStep] = Field(default_factory=dict)
    forward: dict[str, BaseForwardConfig] = Field(default_factory=dict)
    mount: dict[str, BaseMountConfig] = Field(default_factory=dict)


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

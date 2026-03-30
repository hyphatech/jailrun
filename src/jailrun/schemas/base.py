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

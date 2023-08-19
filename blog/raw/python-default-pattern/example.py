import dacite
from dataclasses import dataclass, field

@dataclass
class Cron:
    name: str
    command: str


@dataclass
class BackupConfig:
    enabled: bool
    bucket: str

    @staticmethod
    def default() -> "BackupConfig":
        return BackupConfig(enabled=False, bucket="default")

@dataclass
class HostConfig:
    backup: BackupConfig

    @staticmethod
    def default() -> "HostConfig":
        return HostConfig(
            backup=BackupConfig.default(),
        )

@dataclass
class HostData:
    config: HostConfig = field(default_factory=HostConfig.default)
    cron: list[Cron] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict) -> "HostData":
        return dacite.from_dict(data_class=HostData, data=data, config=dacite.Config(strict=True))


print(HostData.from_dict({}))
print(HostData.from_dict({"cron": [{"name": "do something", "command": "ls"}]}))

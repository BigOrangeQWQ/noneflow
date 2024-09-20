from enum import Enum


class PackageType(Enum):
    BOT = "Bot"
    ADAPTER = "Adapter"
    PLUGIN = "Plugin"

    def __str__(self) -> str:
        return self.value

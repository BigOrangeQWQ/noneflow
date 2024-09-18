from enum import Enum

from pydantic import BaseModel


class PackageType(Enum):
    BOT = "Bot"
    ADAPTER = "Adapter"
    PLUGIN = "Plugin"

    def __str__(self) -> str:
        return self.value


class RemoveInfo(BaseModel):
    module_name: str
    project_link: str
    type: PackageType


class RepoInfo(BaseModel):
    """仓库信息"""

    owner: str
    repo: str

from asyncio import create_subprocess_shell, subprocess
import asyncio
import json
from typing import Any

import docker

from src.utils.constants import DOCKER_IMAGES


class DockerPluginTest:
    def __init__(
        self,
        docker_images: str,
        project_link: str,
        module_name: str,
        config: str = "",
    ):
        self.docker_images = docker_images
        self.project_link = project_link
        self.module_name = module_name
        self.config = config

    @property
    def key(self) -> str:
        """插件的标识符

        project_link:module_name
        例：nonebot-plugin-test:nonebot_plugin_test
        """
        return f"{self.project_link}:{self.module_name}"

    async def run_shell_command(
        self, cmd: str, timeout: int | None = None
    ) -> tuple[bool, str, str]:
        """
        执行命令
        """
        try:
            proc = await create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if timeout:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
            else:
                stdout, stderr = await proc.communicate()
            code = proc.returncode
        except TimeoutError:
            proc.terminate()
            stdout, stderr = b"", "执行命令超时".encode()
            code = 1  # 非 0 返回，代表运行失败

        return not code, stdout.decode(), stderr.decode()

    async def pull_docker_image(self, version: str):
        """
        拉取 docker 镜像
        """
        return await self.run_shell_command(
            f"sudo docker pull {self.docker_images.format(version)}"
        )

    async def run(self, version: str) -> dict[str, Any]:
        image_name = DOCKER_IMAGES.format(version)
        client = docker.DockerClient(
            base_url="unix://var/run/docker.sock"
        )  # 连接 Docker 环境

        client.images.pull(image_name)

        async def runner():
            return client.containers.run(
                image_name,
                environment={"PLUGIN_INFO": self.key, "PLUGIN_CONFIG": self.config},
                detach=True,
            )

        container = await asyncio.wait_for(runner(), 600)

        output = container.logs()

        data = json.loads(output)
        data["config"] = self.config
        data["version"] = version
        return data

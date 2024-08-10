from asyncio import create_subprocess_shell, subprocess
import asyncio
import json
from typing import Any

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
            code = 1 # 非 0 返回，代表运行失败

        return not code, stdout.decode(), stderr.decode()

    async def check_docker_exist(self) -> bool:
        """
        检查是否存在 docker
        """
        return (await self.run_shell_command("docker -v"))[0]

    async def pull_docker_image(self, version: str):
        """
        拉取 docker 镜像
        """
        return await self.run_shell_command(
            f"docker pull {self.docker_images.format(version)}"
        )

    async def run(self, version: str) -> dict[str, Any]:
        if not await self.check_docker_exist():
            raise Exception("运行 Docker 测试失败，请检查 Docker 是否存在")

        # 拉取插件测试镜像
        await self.pull_docker_image(version)

        # 运行容器，开始插件测试
        status, output, _ = await self.run_shell_command(
            f"docker run -e PLUGIN_INFO={self.key} -e PLUGIN_CONFIG={self.config} {self.docker_images.format(version)}",
            timeout=600,
        )

        if status:
            data = json.loads(output)
            data["config"] = self.config
            data["version"] = version
            return data

        raise Exception("运行 Docker 测试失败，可能是 Images 拉取失败或运行错误")


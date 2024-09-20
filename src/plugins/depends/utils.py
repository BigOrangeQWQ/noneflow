import re
import subprocess

from nonebot import logger


def run_shell_command(command: list[str]):
    """运行 shell 命令

    如果遇到错误则抛出异常
    """
    logger.info(f"运行命令: {command}")
    try:
        r = subprocess.run(command, check=True, capture_output=True)
        logger.debug(f"命令输出: \n{r.stdout.decode()}")
    except subprocess.CalledProcessError as e:
        logger.debug("命令运行失败")
        logger.debug(f"命令输出: \n{e.stdout.decode()}")
        logger.debug(f"命令错误: \n{e.stderr.decode()}")
        raise
    return r


def extract_issue_number_from_ref(ref: str) -> int | None:
    """从 Ref 中提取议题号"""
    match = re.search(r"(\w{4,10})\/issue(\d+)", ref)
    if match:
        return int(match.group(2))

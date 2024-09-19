"""
常见的 Git 操作封装
"""

from plugins.publish.utils import run_shell_command


def git_add_all():
    """git add ."""
    return run_shell_command(["git", "add", "-A"])


def git_commit(message: str):
    """git commit"""
    return run_shell_command(["git", "commit", "-m", message])


def git_add_and_commit(message: str):
    """git add . && git commit"""
    return git_add_all(), git_commit(message)


def git_push(branch: str, force: bool = False):
    """git push"""
    cmd = ["git", "push", "origin", branch]
    if force:
        cmd.append("-f")
    return run_shell_command(cmd)


def git_switch_branch(branch: str, create_new: bool = False):
    """git switch branch"""
    cmd = ["git", "switch", branch]
    if create_new:
        cmd = ["git", "switch", "-c", branch]
    return run_shell_command(cmd)

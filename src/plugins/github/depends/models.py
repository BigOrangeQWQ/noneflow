from githubkit.rest import Issue
from nonebot import logger
from pydantic import BaseModel, ConfigDict, computed_field
from nonebot.adapters.github import Bot

from githubkit.exception import RequestFailed

from .utils import run_shell_command
from .constants import NONEFLOW_MARKER


class RepoInfo(BaseModel):
    """仓库信息"""

    owner: str
    repo: str


class IssueHandler(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    bot: Bot
    repo_info: RepoInfo
    issue_number: int
    issue: Issue

    @computed_field(return_type=str)
    @property
    def author(self) -> str:
        return self.issue.user.login if self.issue.user else ""

    @computed_field(return_type=int)
    @property
    def author_id(self) -> int:
        return self.issue.user.id if self.issue.user else 0

    def commit_and_push(self, message: str, branch_name: str):
        run_shell_command(["git", "config", "--global", "user.name", self.author])
        user_email = f"{self.author}@users.noreply.github.com"
        run_shell_command(["git", "config", "--global", "user.email", user_email])
        run_shell_command(["git", "add", "-A"])
        try:
            run_shell_command(["git", "commit", "-m", message])
        except Exception:
            # 如果提交失败，因为是 pre-commit hooks 格式化代码导致的，所以需要再次提交
            run_shell_command(["git", "add", "-A"])
            run_shell_command(["git", "commit", "-m", message])

        try:
            run_shell_command(["git", "fetch", "origin"])
            r = run_shell_command(["git", "diff", f"origin/{branch_name}", branch_name])
            if r.stdout:
                raise Exception
            else:
                logger.info("检测到本地分支与远程分支一致，跳过推送")
        except Exception:
            logger.info("检测到本地分支与远程分支不一致，尝试强制推送")
            run_shell_command(["git", "push", "origin", branch_name, "-f"])

    async def create_pull_request(
        self, base_branch: str, title: str, branch_name: str, label: str
    ):
        body = f"resolve #{self.issue_number}"

        try:
            # 创建拉取请求
            resp = await self.bot.rest.pulls.async_create(
                **self.repo_info.model_dump(),
                title=title,
                body=body,
                base=base_branch,
                head=branch_name,
            )
            pull = resp.parsed_data

            # 自动给拉取请求添加标签
            await self.bot.rest.issues.async_add_labels(
                **self.repo_info.model_dump(),
                issue_number=pull.number,
                labels=[label],
            )
            logger.info("拉取请求创建完毕")
        except RequestFailed:
            logger.info("该分支的拉取请求已创建，请前往查看")

            pull = (
                await self.bot.rest.pulls.async_list(
                    **self.repo_info.model_dump(),
                    head=f"{self.repo_info.owner}:{branch_name}",
                )
            ).parsed_data[0]
            if pull.title != title:
                await self.bot.rest.pulls.async_update(
                    **self.repo_info.model_dump(), pull_number=pull.number, title=title
                )
                logger.info(f"拉取请求标题已修改为 {title}")
            if pull.draft:
                await self.bot.async_graphql(
                    query="""mutation markPullRequestReadyForReview($pullRequestId: ID!) {
                        markPullRequestReadyForReview(input: {pullRequestId: $pullRequestId}) {
                            clientMutationId
                        }
                    }""",
                    variables={"pullRequestId": pull.node_id},
                )
                logger.info("拉取请求已标记为可评审")

    async def comment_issue(self, comment: str):
        logger.info("开始发布评论")

        # 重复利用评论
        # 如果发现之前评论过，直接修改之前的评论
        comments = (
            await self.bot.rest.issues.async_list_comments(
                **self.repo_info.model_dump(), issue_number=self.issue_number
            )
        ).parsed_data
        reusable_comment = next(
            filter(lambda x: NONEFLOW_MARKER in (x.body if x.body else ""), comments),
            None,
        )

        # comment = await render_comment(result, bool(reusable_comment))
        if reusable_comment:
            logger.info(f"发现已有评论 {reusable_comment.id}，正在修改")
            if reusable_comment.body != comment:
                await self.bot.rest.issues.async_update_comment(
                    **self.repo_info.model_dump(),
                    comment_id=reusable_comment.id,
                    body=comment,
                )
                logger.info("评论修改完成")
            else:
                logger.info("评论内容无变化，跳过修改")
        else:
            await self.bot.rest.issues.async_create_comment(
                **self.repo_info.model_dump(),
                issue_number=self.issue_number,
                body=comment,
            )
            logger.info("评论创建完成")

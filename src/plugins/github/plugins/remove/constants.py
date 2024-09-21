import re

from src.plugins.github.constants import ISSUE_PATTERN

REMOVE_HOMEPAGE_PATTERN = re.compile(ISSUE_PATTERN.format("项目地址"))

BRANCH_NAME_PREFIX = "remove/issue"

COMMIT_MESSAGE_PREFIX = ":hammer: remove"

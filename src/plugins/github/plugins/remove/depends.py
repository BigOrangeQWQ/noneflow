from githubkit.rest import (
    PullRequestPropLabelsItems,
    WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems,
    WebhookIssuesEditedPropIssuePropLabelsItems,
    WebhookIssuesOpenedPropIssuePropLabelsItems,
    WebhookIssuesReopenedPropIssueMergedLabels,
    WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems,
)
from githubkit.typing import Missing

from nonebot.params import Depends

from src.plugins.github.depends import get_labels


def get_name_by_labels(
    labels: list[PullRequestPropLabelsItems]
    | list[WebhookPullRequestReviewSubmittedPropPullRequestPropLabelsItems]
    | Missing[list[WebhookIssuesOpenedPropIssuePropLabelsItems]]
    | Missing[list[WebhookIssuesReopenedPropIssueMergedLabels]]
    | Missing[list[WebhookIssuesEditedPropIssuePropLabelsItems]]
    | list[WebhookIssueCommentCreatedPropIssueAllof0PropLabelsItems] = Depends(
        get_labels
    ),
) -> list[str]:
    """通过标签获取名称"""
    label_names = []
    if not labels:
        return label_names

    for label in labels:
        if label.name:
            label_names.append(label.name)
    return label_names

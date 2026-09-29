"""Title policy tests; no network or real conversation inputs."""

import json

import pytest
from langchain_core.messages import AIMessage

from app.titles import checked_title


@pytest.mark.parametrize("title", ["工作压力与睡眠困扰", "Preparing for exams", "朋友相处中的边界"])
def test_title_accepts_short_topic(title: str) -> None:
    assert checked_title(AIMessage(content=json.dumps({"title": title}))) == title


@pytest.mark.parametrize(
    "title",
    [
        "",
        "新的对话",
        "x" * 25,
        " 两端空白 ",
        "多行\n标题",
        "隐藏\u200b字符",
        "联系123456789",
        "me@example.com",
        "https://example.com",
        "确诊抑郁症",
    ],
)
def test_title_rejects_invalid_or_identifying_output(title: str) -> None:
    with pytest.raises(ValueError):
        checked_title(AIMessage(content=json.dumps({"title": title})))


@pytest.mark.parametrize("content", ["plain text", '{"title":"主题","extra":true}', "{}"])
def test_title_requires_exact_schema(content: str) -> None:
    with pytest.raises(ValueError):
        checked_title(AIMessage(content=content))

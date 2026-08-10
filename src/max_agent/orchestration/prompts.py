"""构造编排规划阶段使用的受约束提示词模板。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


def build_planning_prompt() -> ChatPromptTemplate:
    """返回仅描述规划边界的模板，不在此处调用任何模型。"""
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Generate one structured desktop action. Never invent invisible targets.",
            ),
            (
                "human",
                "Goal: {user_goal}\nMode: {reasoning_mode}\n"
                "Observation: {observation}\nRecent steps: {history}",
            ),
        ]
    )

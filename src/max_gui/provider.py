"""主推理 provider 定义：集中维护模型、端点、鉴权来源与运行能力。

对外入口为 `PROVIDERS`、`get_provider`、`resolve_provider` 与
`require_provider_key`。所有 provider 共用 OpenAI 兼容 Chat Completions，
本模块只描述后端差异，不保存真实密钥，也不实现网络客户端。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

DEFAULT_PROVIDER = "ollama"
ThinkingMode = Literal["ollama", "enable_thinking", "openrouter", "qiniu"]


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """一个 OpenAI 兼容推理后端的不可变定义。

    字段：
        name: `.env` 中使用的唯一 provider 名称。
        model_name: 请求使用的固定模型名。
        base_url: OpenAI 兼容 API 根端点，不含 `/chat/completions`。
        api_key_env: 保存密钥的环境变量名；`None` 表示不鉴权。
        key_label: 缺密钥时展示的凭据类型。
        context_window: 主推理上下文容量。
        replay_reasoning: 是否把历史思考回传为 `reasoning_content`。
        thinking_mode: 上游 thinking 开关对应的请求字段模式。
        connection_hint: 网络失败时附加的中文排查提示。

    该对象没有副作用；真实密钥由配置加载阶段另行读取。
    """

    name: str
    model_name: str
    base_url: str
    api_key_env: str | None
    key_label: str
    context_window: int
    replay_reasoning: bool
    thinking_mode: ThinkingMode
    connection_hint: str

    def thinking_payload(self, enabled: bool) -> dict[str, Any]:
        """生成控制本 provider 上游思考的顶层请求字段。

        参数：
            enabled: 为真时请求上游生成思考；为假时显式关闭。

        返回：
            可直接合并至 Chat Completions JSON 顶层的字段。
        """
        match self.thinking_mode:
            case "ollama":
                return {"think": enabled}
            case "enable_thinking":
                return {"enable_thinking": enabled}
            case "openrouter":
                return {"reasoning": {"enabled": enabled}}
            case "qiniu":
                return {"thinking": {"type": "enabled" if enabled else "disabled"}}


_PROVIDER_ITEMS = (
    ProviderDefinition(
        name="ollama",
        model_name="qwen3.5:4b",
        base_url="http://192.168.1.158:11434/v1",
        api_key_env=None,
        key_label="",
        context_window=262_144,
        replay_reasoning=False,
        thinking_mode="ollama",
        connection_hint="请检查 WSL Ollama 服务、Windows 防火墙与局域网端口。",
    ),
    ProviderDefinition(
        name="modelscope",
        model_name="Qwen/Qwen3.8-27B",
        base_url="https://api-inference.modelscope.cn/v1",
        api_key_env="MAX_MODELSCOPE_KEY",
        key_label="魔搭 Access Token",
        context_window=32_768,
        replay_reasoning=False,
        thinking_mode="enable_thinking",
        connection_hint="请检查网络与 MAX_MODELSCOPE_KEY。",
    ),
    ProviderDefinition(
        name="dashscope",
        model_name="qwen3.8-27b",
        base_url=("https://llm-xxcxmbwit4rg4ios.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"),
        api_key_env="MAX_DASHSCOPE_KEY",
        key_label="百炼 API Key",
        context_window=32_768,
        replay_reasoning=True,
        thinking_mode="enable_thinking",
        connection_hint="请检查网络与 MAX_DASHSCOPE_KEY。",
    ),
    ProviderDefinition(
        name="openrouter",
        model_name="qwen/qwen3.5-plus",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="MAX_OPENROUTER_KEY",
        key_label="OpenRouter API Key",
        context_window=32_768,
        replay_reasoning=False,
        thinking_mode="openrouter",
        connection_hint="请检查网络与 MAX_OPENROUTER_KEY。",
    ),
    ProviderDefinition(
        name="qiniu",
        # model_name="qwen/qwen3.5-plus",
        model_name="z-ai/glm-5.3-flash",
        base_url="https://api.qnaigc.com/v1",
        api_key_env="MAX_QINIU_KEY",
        key_label="七牛 AI Token API Key",
        context_window=32_768,
        replay_reasoning=False,
        thinking_mode="qiniu",
        connection_hint="请检查网络与 MAX_QINIU_KEY。",
    ),
)

PROVIDERS: Mapping[str, ProviderDefinition] = MappingProxyType(
    {provider.name: provider for provider in _PROVIDER_ITEMS}
)


class UnknownProviderError(ValueError):
    """`MAX_PROVIDER` 不是注册表中的推理后端。"""

    def __init__(self, raw: str) -> None:
        """用非法原文和注册表允许值构造中文错误。

        参数：
            raw: 用户提供的非法 provider 原文。
        """
        allowed = ", ".join(sorted(PROVIDERS))
        super().__init__(f"未知推理后端：{raw}。可用：{allowed}")


class MissingProviderKeyError(ValueError):
    """需要认证的 provider 缺少自己的密钥环境变量。"""

    def __init__(self, provider: ProviderDefinition) -> None:
        """按 provider 定义生成不会误导到本地服务的中文错误。

        参数：
            provider: 缺少密钥的 provider 定义；调用方保证其需要密钥。
        """
        env_name = provider.api_key_env or ""
        super().__init__(
            f"未设置 {env_name}。使用 {provider.name} 时请在 .env 中填写{provider.key_label}。"
        )


def get_provider(name: str) -> ProviderDefinition:
    """按规范化名称取得 provider 定义。

    参数：
        name: 已去空白并转小写的 provider 名称。

    返回：
        注册表中的不可变定义。

    异常：
        UnknownProviderError: 名称未注册。
    """
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise UnknownProviderError(name) from exc


def resolve_provider(raw: str | None) -> ProviderDefinition:
    """规范化 `MAX_PROVIDER` 原文并返回对应定义。

    参数：
        raw: 环境变量原文；空值选择 `ollama`。

    返回：
        注册表中的不可变定义。

    异常：
        UnknownProviderError: 规范化后的名称未注册。
    """
    name = (raw or DEFAULT_PROVIDER).strip().lower()
    return get_provider(name)


def has_provider_key(api_key: str) -> bool:
    """判断密钥是否非空且不是历史占位值 `EMPTY`。

    参数：
        api_key: 配置解析后的密钥字符串。

    返回：
        可作为 Bearer 密钥时为真。
    """
    key = api_key.strip()
    return bool(key) and key != "EMPTY"


def require_provider_key(provider: ProviderDefinition, api_key: str) -> None:
    """验证需要鉴权的 provider 已取得专属密钥。

    参数：
        provider: 当前 provider 定义。
        api_key: 从定义指定的环境变量解析出的密钥。

    异常：
        MissingProviderKeyError: provider 需要密钥但当前值不可用。
    """
    if provider.api_key_env is not None and not has_provider_key(api_key):
        raise MissingProviderKeyError(provider)

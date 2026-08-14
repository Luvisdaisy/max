## 1. 会话持久化坐标系

- [x] 1.1 给 `Session` 增加 `view_frame` / `locate_hits`，旧 JSON 缺字段仍能加载
- [x] 1.2 提供 `ViewFrame` 与 hits 的序列化、写入 ContextVar、从会话恢复
- [x] 1.3 `AgentRunner.run` 开头恢复、`_persist` 写回会话

## 2. 截图摘要与流式错误

- [x] 2.1 摘要 `cursor` 改为视图像素；`region` schema 标明逻辑像素
- [x] 2.2 流式 HTTP 非 2xx 用 `aread()` 取正文，错误含状态码

## 3. 默认 4B

- [x] 3.1 `DEFAULT_MODEL_ALIAS` 与 CLI 帮助改为 `qwen3.5-4b`
- [x] 3.2 测试夹具仍钉死 2B；补 `load_settings` 默认 4B 与跨回合换算 / 流式错误用例

## 4. 文档与校验

- [x] 4.1 更新 `AGENTS.md`、`README.md` 中的默认模型与坐标系说明
- [x] 4.2 `uv run ruff format/check` 与 `uv run pytest`

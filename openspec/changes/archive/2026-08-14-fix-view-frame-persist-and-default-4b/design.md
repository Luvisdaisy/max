## Context

`screenshot` 把 `ViewFrame` 写进 `ContextVar`。TUI 每回合 `run_worker` 新开任务，下一句用户话再 `mouse_*` 时 `frame is None`，坐标被当成逻辑像素。`ocr_locate` 的 hits 同样丢失。摘要里 `cursor` 仍是逻辑坐标，却标 `coordinate_space=view`。流式客户端在 `client.stream()` 里遇到非 2xx 后读 `response.text`，httpx 抛内部异常。默认模型仍是 2B。

## Goals / Non-Goals

**Goals:**

- 同一会话内，截图后的下一回合（含进程重启后恢复该会话）仍按视图像素换算。
- `ocr_locate` 的 `target_id` 跨回合可用，直到下一次定位覆盖。
- 摘要 `cursor` 与模型看见的图像素对齐。
- HTTP 失败展示状态码与正文片段。
- 默认 `serve` / TUI / `download` 走 `qwen3.5-4b`。

**Non-Goals:**

- 不改 tool 角色带图的编码方式（另议）。
- 不加系统提示强制 `ocr_locate`。
- 不自动重启已在跑的 vLLM；改默认后需重新 `max-gui serve`。
- 不把测试夹具从 2B 占位权重改成 4B。

## Decisions

1. **坐标系落在 Session，不靠进程字典。**  
   `Session.view_frame` / `Session.locate_hits` 写入 JSON。`AgentRunner.run` 开头从会话恢复 `ContextVar`，`_persist` 再写回。  
   - 备选：模块级 `dict[session_id, ViewFrame]`。不采用：重启 TUI 后仍丢。  
   - 备选：只塞进 checkpoint。不采用：checkpoint 在 `done` 后语义含混，且工具层不该只认识图状态。

2. **旧会话缺字段视为尚无截图。**  
   `from_dict` 缺 `view_frame` / `locate_hits` 时为 `None` / `{}`，行为与现在冷启动一致。

3. **`cursor` 用当前帧换算成视图像素。**  
   `view = (logical - origin) * view_size / logical_size`。区域外光标可以落在视图外，仍报告换算值，不夹紧。`region` 参数说明写明逻辑像素，不改解析。

4. **流式错误 `aread()`。**  
   `HTTPStatusError` 时 `await response.aread()`，解码后截断 400 字；再失败则用 `str(exc)`。

5. **默认别名改 `qwen3.5-4b`。**  
   `DEFAULT_MODEL_ALIAS`、CLI 帮助、主规格与 README/AGENTS。`2b` 别名保留。测试 `Settings` 仍显式 `qwen3.5-2b`，避免夹具依赖 4B 真权重。`load_settings()` 无覆盖时的默认用例单独测。

## Risks / Trade-offs

- [Risk] 会话 JSON 里的截图路径失效 → 仍恢复宽高与原点，换算可用；图缺失只影响回注。
- [Risk] 4B 显存比 2B 高 → 本机已有权重；OOM 时用户可 `--model 2b`。
- [Risk] 已启动的 vLLM 仍是 2B → 文档写明需重启 `max-gui serve`。
- [Risk] 2B 模型仍会猜错坐标 → 本次只修运行时；4B 降低误猜，不保证点准。

## Migration Plan

改代码与规格后跑 ruff / pytest。已有会话无新字段仍可加载。切换默认模型后重新执行 `max-gui serve`。回滚：把 `DEFAULT_MODEL_ALIAS` 改回 `qwen3.5-2b`，坐标系字段可留。

## Open Questions

无。

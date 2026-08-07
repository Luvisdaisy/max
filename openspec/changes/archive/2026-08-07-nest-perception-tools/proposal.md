## Why

项目已明确以 Agent Orchestrator 为核心、其余能力通过工具/插件提供。将未来的屏幕感知能力放在独立顶层 `perception` 会弱化这一边界，并造成工具注册、权限和测试入口分散。

## What Changes

- 将未来感知实现的规范位置确定为 `src/max_agent/tools/perception/`，由 `tools` 统一承载所有可由编排器调用的能力。
- 保留 `tools` 下的工具契约与注册表；感知目录仅按领域组织多个独立工具，不形成可绕过编排器的聚合执行器。
- 同步根目录技术设计中的目录结构、职责边界和工具命名，说明当前仓库尚无需要移动的感知实现。
- 改善桌面探针：`doctor --desktop-probe` 保持显式可选，并仅在显式安全地请求临时窗口成为前台后才发送输入；无法取得前台焦点时跳过且不发送输入。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-bootstrap`: 明确桌面探针会在显式选项下有限地请求临时受控窗口获得前台焦点，并为前台焦点不可用的跳过结果提供可操作说明。

## Impact

- 影响 `tech-design.md` 的未来目录和模块职责说明。
- 后续实现感知工具时，代码应创建在 `src/max_agent/tools/perception/`，而不是新增顶层 `perception` 包；当前没有需要移动的感知实现。
- 影响 `src/max_agent/diagnostics.py` 的显式桌面探针前台焦点请求和跳过提示；不改变公开 CLI 或新增依赖。

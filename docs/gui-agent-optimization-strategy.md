# 下一步优化策略：先补控制策略与评测，再谈 LoRA

日期：2026-08-17  
范围：对照 [实习项目大纲](大模型%20AI%20Agent%20算法岗位线上实习项目大纲.md) 与当前仓库实现，给出 ReAct GUI Agent 的下一阶段优化顺序。本文是策略报告，不是已落地规格。桌面工具约定见 [gui-tools.md](gui-tools.md)，数据层设计见 [gui-datasets-week3.md](gui-datasets-week3.md)。

## 判断

当前仓库已经把大纲第 1–4 周的**工程骨架**做完：感知（截图回注、OCR）、控制（键鼠）、LangGraph ReAct、vLLM、TUI、会话。真正缺的不是再堆工具，而是 **GUI 专用的 ReAct 控制策略、上下文治理、可复现评测，以及第三周留下的数据层**。

**不要立刻做第 5 周 LoRA。** 现在微调几乎量不出收益：没有基线任务集，没有系统提示与规划策略，4B 还在「裸 Function Calling」上碰运气。先把可测闭环立住，再用同一套指标对比「提示词 / 规划 / LoRA」。

---

## 大纲进度 vs 仓库现状

| 周 | 大纲要求 | 现状 | 缺口性质 |
| --- | --- | --- | --- |
| 1 | 调研 + 环境 | [gui-tools.md](gui-tools.md)、vLLM/Metal 已就绪 | 可补一篇对照 Ui-TARS / Computer Use 的短调研，不挡开发 |
| 2 | 截图 / OCR / 键鼠 / 画框 | 桌面工具 + `ocr` / `ocr_locate` + 视图像素换算已归档 | 已完成；无障碍控件树、多屏、找窗仍刻意不做 |
| 3 | 公开数据预处理 + Agent 框架 + 任务拆解 | 框架有；状态含轻量 `plan` / `current_subtask`；数据脚本没有 | **半完成**。见 [gui-datasets-week3.md](gui-datasets-week3.md) |
| 4 | 感知+控制+Agent 闭环 + 5 个基础任务报告 | REPL 闭环有；GUI system、动作后回注、最近两张图已落地；`test_e2e_chain` 只测 stub 文本 | **无 5 任务验收** |
| 5 | ScreenAgent 等 LoRA + 提示词对比 | 未开始 | 缺训练集 JSONL 与对比基线 |
| 6 | 拆解、重试、感知加速、执行日志 | `max_iterations` 默认 20；tool 消息含 `exec`（不另写 `artifacts/runs/`） | 无同屏熔断 / 工具自动重试 |
| 7–8 | 20 任务评估、技术报告、演示 | 未开始 | 依赖前面的评测夹具 |

---

## 架构上真正卡住成功率的点

```text
用户指令
    │
    ▼
[GUI system + 轻量 plan] ──► think（4B，tool_choice=auto）
    │
    ├─ 协议要求先截图、坐标用最近一帧；模型仍可能不遵守
    ├─ 变异动作成功后运行时附新图；仍无同屏空转熔断
    ├─ 请求只编码最近两张图；max_model_len 仍为 8192
    └─ 默认 20 轮硬停；无工具自动重试
            │
            ▼
      仍无法回答：提示词改了有没有用？该不该微调？（缺 5 任务基线）
```

对照代码（第 1 期 `gui-react-control-policy` 已归档）：

- `think` 注入中文 GUI `system`（不落盘）；状态含 `plan` / `current_subtask`，图拓扑仍是 `think ⇄ act → observe`。
- `to_chat_messages` 只把最近两张仍存在的图编成 `image_url`。
- `max_iterations` 默认 20；`max_model_len` 仍为 8192。
- 点击/拖拽/滚轮/输入/按键成功后在同一条工具结果附新截图。
- 会话 tool 消息含 `name` 与嵌套 `exec`；没有独立 `artifacts/runs/` JSONL。
- 仍缺：同屏连点熔断、工具错误自动重试、5 任务可复现评测。

工具层本身（坐标系、确认门、假后端）已经够用，继续加 `mss` / EasyOCR / 控件检测的边际收益低于补评测与鲁棒性。

---

## 推荐路线：三期，按杠杆排序

原则：每一期都必须留下**可对比的数字**（成功率、步数、超时、是否改屏），避免「感觉更好了」。落地仍走 OpenSpec，一期一个 change，不要把数据、规划、LoRA 塞进同一变更。

### 第 1 期（已落地）：让现有 4B 按 GUI 协议跑

目标：不换模型、不训权重，先把「看 → 想 → 动 → 再看」写成硬约束。对应大纲第 4 周补课 + 第 6 周的策略部分。

1. **GUI 系统提示 + 动作契约**  
   固定注入中文 system：必须先 `screenshot`；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`；看不清字再 OCR；破坏性动作一次一个；动作后必须再截图再判断是否进入下一子任务。  
   这是当前投资回报最高的一行改动。

2. **上下文治理**  
   发给模型时只保留最近 1–2 张图的 `image_url`，更早截图改成路径/尺寸摘要。否则 2–3 轮就会顶满 8k。迭代上限对桌面任务单独放到约 20，并区分「模型还在干活」和「同屏空转」。

3. **轻量 Plan / Reflect，先不要新框架**  
   不要先拆第二个图或换 LangChain。在现有图上二选一（建议先 A）：
   - **A.** 系统提示要求首轮只输出编号子任务，状态里记下 `plan` / `current_subtask`；每步观察后用规则或短提示判定继续 / 重试 / 改计划（对齐 ScreenAgent 的 Plan / Act / Evaluate）。
   - **B.** 加独立 `plan` 节点。行为更清晰，但要改 OpenSpec 的 `react-agent` 规格，放到 1 期后半或 2 期。

4. **动作后强制观察**  
   `mouse_click` / `keyboard_*` / `mouse_drag` / `mouse_scroll` 成功后，由运行时自动补一次截图回注（或强约束模型下一步必须截图）。没有「执行后画面」，4B 无法做错误检测。

5. **结构化执行日志**  
   落地为会话 tool 消息的 `exec`（迭代、子任务、参数、耗时、错误、是否新图），不另写 `artifacts/runs/`。TUI 记录区只显示工具文本。同屏熔断与独立 JSONL 统计仍留到后续。

验收：同一条「打开计算器并算 1+1」，改提示词前后都能从会话 `exec` 里数出：是否先截图、点击后是否复检、是否在上限内停。

### 第 2 期（紧接着）：数据对齐 + 5 任务基线

对应大纲第 3 周未做部分 + 第 4 周交付物。设计已写在 [gui-datasets-week3.md](gui-datasets-week3.md)，按文档做即可，不要另起数据格式。

1. Sparse checkout ScreenAgent `data/ScreenAgent`，解压 test；下载 WebArena `test.raw.json`。数据落 `artifacts/datasets/`，不进 git。
2. 预处理脚本：正例 → 统一 JSONL（`stage=plan|act|reflect` + 工具名映射）；丢掉 `*_neg_plan`；坐标保持 1024×768 图像素，**执行时再换算**。
3. 从 train 抽 3–5 条 `PlanAction` 进 system few-shot；抽 10 条 act 人工对图核坐标，作为脚本验收。
4. **5 个基础桌面任务卡**（打开浏览器、搜索指定内容、打开指定文件、发送消息、关闭应用），每条写：前置、成功判定（功能结果，不要求轨迹逐点相同）、超时、最大步数。跑脚本出第 4 周测试报告：成功率、平均步数、平均耗时、失败原因标签（坐标偏 / 没截图 / 焦点打到终端 / 迭代用尽 / 模型提前收工）。
5. WebArena 只生成任务卡 JSONL，本阶段不搭 Docker 站点。Mind2Web 继续可选。

验收：`processed/train.jsonl` 可统计；5 任务有数字基线。没有这条基线，第 5 周「微调前后对比」写不出来。

### 第 3 期（有基线之后）：LoRA 与鲁棒性

对应大纲第 5–7 周，顺序仍是「先能量化，再改权重」。

1. **LoRA（第 5 周）**  
   监督目标用 ScreenAgent `LLM_response_editer_zh` 映射后的工具调用，不要跟对方 CogAgent 脚本。建议先只训 `act` 步（看图选工具+坐标），规划继续靠提示词；2B/4B 选一张显存够的做对照。必须和「第 1+2 期未微调」跑同一 5 任务（或同一抽样子集）。

2. **鲁棒性（第 6 周）**  
   在日志标签驱动下加：同屏重复动作熔断、工具错误自动重试（有上限）、OCR 懒加载/超时已有则只做耗时统计与失败跳过策略收紧。感知加速（mss、更小预览图）只在评测显示「截图/OCR 占时」时再做。

3. **20 任务评估（第 7 周）**  
   沿用任务卡协议，按应用类型与分辨率分层；对比项写清：本仓库 vs 论文数字（Ui-TARS / Computer Use）是**能力差距讨论**，不要假装同基准可复现。

---

## 明确先不要做

- 把 LangGraph 换成 LangChain / LlamaIndex（大纲点名框架，仓库已用更合适的图）。
- 为第三周去跑 ScreenAgent VNC 或 WebArena 全套网站。
- 在没有 JSONL 和 5 任务基线时启动 PEFT。
- 再加一批桌面工具（找窗、控件树、CDP、多屏）。第 2 期 5 任务若大量死在「焦点在终端」，再单独开一个「短暂延迟 / 用户切窗提示」的小变更。
- 混入 COCO / Rico / 通用 VQA 数据。

---

## 建议的下一个 OpenSpec change

第 1 期 `gui-react-control-policy` 已归档。下一步倾向：`gui-dataset-preprocess-and-baseline`（第 2 期）。

范围：ScreenAgent / WebArena 预处理、5 个基础桌面任务卡与数字基线。  
不包含：LoRA、新桌面工具、同屏熔断（第 3 期鲁棒性）。

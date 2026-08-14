# 第三周公开 GUI 数据集调研：ScreenAgent 与 WebArena

日期：2026-08-14  
范围：对照实习大纲第三周「下载并预处理 ScreenAgent、WebArena、Mind2Web 等公开 GUI 任务数据集」，说明这两个仓库分别是什么、能给本仓库做什么、第三周该怎么落地。第三周还要求搭 Agent 框架与模型接口；本仓库这部分已经有 LangGraph ReAct + vLLM，本文只点明缺口，不重复写框架设计。桌面工具调研见 [gui-tools.md](gui-tools.md)。

来源：

- [ScreenAgent README](https://github.com/niuzaisheng/ScreenAgent/blob/main/README.md) / [中文说明](https://github.com/niuzaisheng/ScreenAgent/blob/main/README-zh.md)，论文 [arxiv:2402.07945](https://arxiv.org/abs/2402.07945)
- [WebArena README](https://github.com/web-arena-x/webarena/blob/main/README.md)，论文 [arxiv:2307.13854](https://arxiv.org/abs/2307.13854)
- 仓库内实测：ScreenAgent `data/ScreenAgent/train` 目录结构与样本 JSON；WebArena `config_files/test.raw.json`（812 条）

## 结论

这两个仓库都被大纲写成「数据集」，但性质不同，不能按同一种方式下载、预处理、微调。

| 仓库 | 本质 | 对本项目的用处 | 第三周该不该全量跑通 |
| --- | --- | --- | --- |
| ScreenAgent | 桌面截图 + 人工修正轨迹，附带 VNC 控制器与微调代码 | **主训练集**。教模型看 1024×768 截图、拆子任务、输出坐标级键鼠动作 | 要。下载 train/test，转成统一样本，映射到现有桌面工具 |
| WebArena | 可自建的真实网站评测环境 + 812 条任务定义 | **评测集 / 任务卡**。长程网页任务、功能正确性指标、规划提示词样例 | 不要在第三周搭整套网站。先解析任务 JSON；完整环境留给后续评测 |

第三周对数据的最低交付：一份不进 git 的本地数据目录 + 预处理脚本，产出可给 Agent 做 few-shot、可给第五周 LoRA 用的统一 JSONL。不要为了「用数据集」去克隆对方的 VNC / Playwright 运行时，也不要把已有 LangGraph 换成 LangChain。

大纲里并列的 Mind2Web 是真实网站操作轨迹（指令 + DOM/截图 + 点击元素），更接近网页版 ScreenAgent。ScreenAgent 仓库里已经有转换脚本；第三周若时间紧，可只做 ScreenAgent，Mind2Web 作为可选加料。

## 第三周任务到底要数据干什么

大纲第三周四件事：

1. 下载并预处理公开 GUI 任务数据
2. 搭多模态 Agent 框架
3. 简单任务拆解与规划
4. 大模型本地 / API 调用

第五周才「基于预处理后的公开 GUI 数据集做 LoRA」。所以第三周不是把 812 条 WebArena 任务在浏览器里跑完，而是把数据变成后面能用的中间表示。

对本仓库，数据要服务三件事：

1. **规划示范**：用户目标 → 子任务列表。ScreenAgent 的 `PlanAction` 会话直接能用。
2. **动作对齐**：截图 + 当前子任务 → 一条可执行动作。ScreenAgent 的 `MouseAction` / `KeyboardAction` 与现有 `mouse_click`、`keyboard_type` 同构。
3. **评测意图**：WebArena 的 `intent` + `eval` 提供「怎样算做对」的任务卡，供第四、七周写桌面/网页测试集时借鉴，而不是第三周的训练像素。

本仓库已具备：截图回注、逻辑坐标桌面工具、OCR、LangGraph ReAct、OpenAI 兼容 vLLM。缺的是「公开轨迹 → 我们的工具协议」这一层，不是再造一套控制器。

## ScreenAgent：桌面轨迹，几乎就是本项目的数据形态

### 它是什么

吉林大学团队的 IJCAI 2024 工作。仓库里同时有：

- **环境**：VNC 连真实桌面，Agent 只看截图、输出键鼠（参考 VNC 协议，点哪里要给坐标，而不是调应用 API）
- **流程**：计划 → 执行 → 反思，循环到任务结束
- **数据集**：人工标注的 session（截图 + 提示词 + 模型原稿 + 人工修正稿 + 解析后的动作）
- **训练**：在 CogAgent 上混训 ScreenAgent / COCO 定位 / Rico 控件说明 / Mind2Web

许可：代码 MIT，数据集 Apache-2.0，模型走 CogVLM 协议。

论文规模：273 个完整 session；训练 203 个 session、3005 张图；测试 70 个 session、898 张图。任务覆盖文件操作、网页浏览、娱乐等日常桌面场景。最复杂规划约 13 步，约 60% 任务规划 3–5 步。

仓库现状（2026-08 核对）：

- 训练集在 GitHub：`data/ScreenAgent/train/<session_id>/`
- 测试集打包：`data/ScreenAgent/test.zip`，约 50 MB
- 训练侧 203 个 session、约 3005 个 JSON、2004 张 jpg
- 每个时间戳通常有 `*_translate.json`（正例）和部分 `*_translate_neg_plan.json`（规划负例，对应 README 里说的 RLHF reject/choice）

### 一条样本长什么样

分辨率固定 **1024×768**。坐标写在 `mouse_position.width` / `height` 里，实际是相对左上角的 `(x, y)`，不是框的宽高。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `task_prompt` / `_zh` / `_en` | 总目标，如「上网查找冯诺依曼的相关资料」 |
| `send_prompt_*` | 发给模型的完整提示（含屏幕尺寸、总目标、子任务、合法动作 JSON schema） |
| `LLM_response` | 模型原稿（reject） |
| `LLM_response_editer_*` | 人工修正稿（choice），第三周 / 第五周监督目标用这个 |
| `saved_image_name` | 同 session 的 `images/` 下截图 |
| `actions` | 从修正稿解析出的动作列表 |

抽查一个 session 的动作类型，正例里常见：

- `PlanAction`：拆子任务
- `MouseAction`：click / double_click / move / scroll / drag
- `KeyboardAction`：打字或按键
- `EvaluateSubTaskAction`：反思当前子任务是否完成（继续 / 重试 / 改计划）

执行步示例（已从仓库样本核对）：

```json
{
  "action_type": "MouseAction",
  "mouse_action_type": "click",
  "mouse_button": "left",
  "mouse_position": {"width": 368, "height": 319}
}
```

这与本仓库 `mouse_click(x=368, y=319)` 是同一类动作。差别只有坐标系：对方在 1024×768 像素图上标点；我们的 PyAutoGUI 工具用**逻辑像素**，Retina 上必须按 `scale` 换算，不能把数据集坐标直接拿去点本机屏幕。

### 对本项目怎么用

**该用的：**

1. 第三周预处理：把每个 JSON + 对应 jpg 打成统一样本  
   `{stage, instruction, image, target_text, actions[]}`  
   `stage` 取 plan / act / reflect，从 `action_type` 判断即可。
2. 动作映射到现有工具，而不是再实现一套 VNC：

   | ScreenAgent | max-gui 工具 |
   | --- | --- |
   | `MouseAction.click` | `mouse_click` |
   | `MouseAction.double_click` | `mouse_click`（double） |
   | `MouseAction.move` | `mouse_move` |
   | `MouseAction` 拖拽 | `mouse_drag` |
   | `KeyboardAction` 文本 | `keyboard_type` |
   | `KeyboardAction` 单键 | `keyboard_press` |
   | `PlanAction` | 不调工具，作为规划文本 / 系统提示示范 |
   | `EvaluateSubTaskAction` | 不调工具，作为反思示范 |

3. 第三周规划能力：从 `PlanAction` 步抽出「总目标 → 编号子任务」，做成 few-shot，不必先微调。
4. 第五周 LoRA：监督目标用 `LLM_response_editer_zh`（本仓库用户可见文案是中文）。图走现有最长边 / 字节限制。负例 JSON 可留到对比学习，第一版 SFT 先丢掉。

**不该用的：**

- 不要为第三周去跑 `niuniushan/screenagent-env` 和 PyQt 控制器。本仓库已经用本机 PyAutoGUI 做同一件事。
- 不要按他们的 `finetune_ScreenAgent.sh` 去训 CogAgent SAT 权重。第五周应对齐本仓库默认的 Qwen 多模态 + PEFT。
- 不要把 COCO / Rico 一并下载。那是他们补视觉定位的混训数据，不是大纲第三周的 GUI 任务集。

### 建议下载方式

数据不要进 git（`.gitignore` 已忽略 `artifacts/`）。

```text
artifacts/datasets/screenagent/
  train/          # git clone 后只保留 data/ScreenAgent/train，或 sparse checkout
  test/           # 解压 data/ScreenAgent/test.zip
  processed/      # 预处理脚本输出（jsonl + 可选缩略图索引）
```

训练集在 GitHub 树上，整仓约很大（含图）。实用做法：

1. `git clone --filter=blob:none --sparse https://github.com/niuzaisheng/ScreenAgent.git`
2. sparse checkout 只开 `data/ScreenAgent`
3. 解压 `test.zip`

或按 session 目录用 GitHub raw / API 拉，但 2000+ 文件不适合手搓。

## WebArena：网站评测场，不是截图微调包

### 它是什么

CMU 等团队的网页 Agent 基准（2023）。仓库主体是：

- 可自托管的四个业务站：电商（Shopping）、论坛（Reddit 仿盘）、GitLab、内容管理（Shopping Admin），外加地图与离线 Wikipedia
- 类 Gym 的 Playwright 浏览器环境：`reset` / `step`，观测默认是 **accessibility tree**（也可截图）
- **812** 条测试任务（`config_files/test.raw.json`，发布 v0.2.0 后标注相对稳定）
- 约 **190** 个意图模板，用槽位实例化（如 “What is the top-{{n}} best-selling product in {{year}}”）
- 官方强调：要复现论文数字必须自建站点；演示站只供浏览

许可：Apache-2.0。

2026-08 核对 `test.raw.json`：

| 站点组合 | 条数（约） |
| --- | --- |
| shopping | 187 |
| shopping_admin | 182 |
| gitlab | 180 |
| map | 109 |
| reddit | 106 |
| 跨站（如 wikipedia+map、gitlab+reddit） | 48 |

812 条全部 `require_login: true`。评估类型可叠加：`program_html` 411、`string_match` 335、`url_match` 205。看的是**功能是否完成**（答案字符串、最终 URL、页面 DOM 断言），不是逐步点击是否长得像人类。

论文基线：GPT-4 + CoT 端到端成功率约 14.41%，人类约 78.24%（人类轨迹约 179 条，Playwright trace）。动作空间是网页元素 id 上的 click / type / hover 等，**不是桌面像素坐标**。

官方已提示：论文级复现仍以本仓为准；新实验更推荐 [AgentLab](https://github.com/ServiceNow/AgentLab/) + BrowserGym（含 VisualWebArena）。

### 一条任务长什么样

```json
{
  "task_id": 0,
  "sites": ["shopping_admin"],
  "intent": "What is the top-1 best-selling product in 2022",
  "intent_template": "What is the top-{{n}} best-selling product in {{year}}",
  "start_url": "__SHOPPING_ADMIN__",
  "eval": {
    "eval_types": ["string_match"],
    "reference_answers": {"exact_match": "Quest Lumaflex™ Band"}
  }
}
```

仓库里**没有**随任务附带逐步截图监督标签。轨迹在 Google Drive 的执行记录 / 人类 trace 里，是评测回放，不是现成 SFT 图文对。

### 对本项目怎么用

**第三周该做：**

1. 只下载 `config_files/test.raw.json`（约 880 KB），解析成任务卡：`task_id`、站点、中文/英文意图、评估类型、参考答案。
2. 用意图做规划拆解的测试输入（「查 2022 销量第一的商品」→ 打开后台、进报表、读表）。不必真连 Magento。
3. 记下评估协议：成功 = 功能结果对，不是动作序列完全一致。第四、七周写 5 / 20 个桌面任务时沿用这一条。

**第三周不要做：**

- 不要为了「预处理数据集」去起整套 Docker / AMI。那是评测基建，磁盘和运维成本远超一周实习额度。
- 不要把 812 条 intent 直接当桌面微调标签。没有对齐过的截图，LoRA 只会背英文任务句。
- 不要把 WebArena 的 `click [id]` 动作空间混进本仓库工具协议。桌面路径继续用坐标；若以后做网页，应另开 DOM / a11y 工具，而不是假装成 `mouse_click`。

**以后若要认真评网页 Agent：**

1. 按官方 `environment_docker` 自建站点并 `generate_test_data.py`
2. 先跑个位数 task_id 打通 `reset` → 观测 → 动作 → `eval`
3. 或改用 VisualWebArena / AgentLab，观测更接近本仓库的「看图」设定
4. 人类 179 条 trace 可作过程示范，但要自己从 Playwright trace 抽帧

## 和 Mind2Web 的分工（大纲点了名，但本次只要求前两个）

| | ScreenAgent | WebArena | Mind2Web |
| --- | --- | --- | --- |
| 界面 | 真实桌面截图 | 自托管网站 | 真实互联网站点快照 |
| 监督 | 逐步截图 + 键鼠坐标 + 规划/反思 | 任务级功能答案，逐步轨迹另存 | 逐步点击哪个元素（DOM + 可选截图） |
| 规模 | 273 session / ~3900 图 | 812 评测任务 | 约 2000 任务 / 137 站（论文口径） |
| 第三周 | **必做预处理** | **只处理任务 JSON** | 可选；HF `osunlp/Mind2Web`，截图需 Globus |
| 第五周 LoRA | 主数据 | 基本不用 | 若要补网页定位再加 |

ScreenAgent 的 `data/Mind2Web/convert_dataset.py` 会拉 HF 并翻译指令；截图包很大。没有翻译 API、没有磁盘预算时，第三周跳过即可。

## 建议的统一中间格式

预处理脚本只产出一种 JSONL，供规划 few-shot 和第五周 SFT 共用。原始 zip / git 树留在 `artifacts/datasets/`，处理后的文件也放那里。

```json
{
  "source": "screenagent",
  "split": "train",
  "session_id": "02ea503d419c440cbda9e42263706d6a",
  "stage": "act",
  "instruction": "上网查找冯诺依曼的相关资料",
  "subtask": "浏览搜索结果，点击感兴趣的链接继续深入了解",
  "image": "artifacts/datasets/screenagent/train/.../2023-12-20_19-35-47-115314.jpg",
  "image_size": [1024, 768],
  "target": "根据现有屏幕图像的状态……",
  "actions": [
    {
      "tool": "mouse_click",
      "args": {"x": 368, "y": 319, "button": "left"}
    }
  ]
}
```

WebArena 另写一张任务表，不要硬塞进上面的 `actions`：

```json
{
  "source": "webarena",
  "task_id": 0,
  "sites": ["shopping_admin"],
  "instruction": "What is the top-1 best-selling product in 2022",
  "eval_types": ["string_match"],
  "reference": "Quest Lumaflex™ Band"
}
```

脚本职责建议控制在：

1. 扫描 ScreenAgent train/test，跳过 `*_neg_plan.json`
2. 按 `actions[0].action_type` 打 stage
3. 坐标与工具名映射；非法 / 缺图样本记入报告后丢弃
4. 写出 `train.jsonl` / `test.jsonl` 和一份中文统计（session 数、各 stage 条数、动作频次）
5. 解析 WebArena `test.raw.json` 为 `webarena_tasks.jsonl`

不要在预处理里启动浏览器、VNC 或模型。

## 和本仓库现状的对齐

| 大纲第三周条目 | 现状 | 数据侧接下来做什么 |
| --- | --- | --- |
| 预处理公开数据集 | 未做 | 按上一节写脚本，数据落 `artifacts/datasets/` |
| LangChain / LlamaIndex 框架 | 已有 LangGraph ReAct | 不换框架；用 ScreenAgent 规划样本加强系统提示即可 |
| 任务拆解与规划 | ReAct 多轮，无显式 plan 节点 | 先用 `PlanAction` few-shot；若要独立 plan 节点，另开 OpenSpec |
| 本地多模态调用 | vLLM + `qwen3.5-2b` | 用处理后的 act 样本做离线「看图选动作」抽查，验证数据没转坏 |

坐标提醒：数据集是 1024×768 图坐标；本机执行必须经 `screen_info` 的 `scale` 与当前分辨率变换。第三周预处理只保留原图像素坐标，转换放到执行器，避免训练和评测各算各的。

## 风险与合规

- 数据集仅用于学习研究，大纲已禁止商用。引用时保留 ScreenAgent / WebArena 论文与 Apache-2.0 声明。
- 原始图不要提交；`artifacts/` 已忽略。
- WebArena 站点含登录态与可写业务数据，评测后需按官方文档复位，不要拿演示站刷 812 条。
- ScreenAgent 轨迹里的网页内容、桌面文件名可能含标注时的环境信息，预处理不要再上传到公共服务。
- 完整复现对方训练（CogAgent SAT + 多卡）与本仓库 2B 本地路线无关，第五周也不建议跟。

## 第三周推荐工作顺序

1. Sparse checkout ScreenAgent 的 `data/ScreenAgent`，解压 `test.zip`，确认 203 + 70 个 session 齐。
2. 下载 WebArena `config_files/test.raw.json`，生成任务卡 JSONL。
3. 写预处理脚本：ScreenAgent → 统一 JSONL + 统计；动作映射表写进脚本注释或本文件，改映射先改文档。
4. 从 train 里抽 10 条 plan、10 条 act，人工看图核对坐标和中文目标，作为脚本的验收。
5. 把 3–5 条 plan 样本接到现有系统提示，用本机截图跑一条「打开浏览器并搜索」类任务，验证数据格式能被 Agent 读懂。
6. Mind2Web、WebArena Docker、LoRA 训练都不要挤进第三周。

## 参考

- Niu et al. ScreenAgent: A Vision Language Model-driven Computer Control Agent. arXiv:2402.07945. 数据与代码：https://github.com/niuzaisheng/ScreenAgent
- Zhou et al. WebArena: A Realistic Web Environment for Building Autonomous Agents. arXiv:2307.13854. 代码：https://github.com/web-arena-x/webarena ；主页：https://webarena.dev
- Mind2Web：https://osu-nlp-group.github.io/Mind2Web/ ；HF：`osunlp/Mind2Web`
- 本仓库桌面工具约定：[gui-tools.md](gui-tools.md)

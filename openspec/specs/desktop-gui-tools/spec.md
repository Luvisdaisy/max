# desktop-gui-tools Specification

## Purpose

基于 PyAutoGUI 的桌面感知与执行（截图、屏幕信息、移鼠、点按、拖拽、滚轮、输入文本、按键），含视图像素换算、权限错误与安全约束。
## Requirements
### Requirement: 截取主屏并返回逻辑元数据

`screenshot` MUST 截取主屏（或给定逻辑像素 `region`），把 PNG 写入 `artifacts/screenshots/`，并返回文本摘要：路径、逻辑宽高、发给主模型后的视图宽高、区域逻辑原点、`scale`、当前光标的**视图像素**坐标，以及 `coordinate_space` 为 `view`。全黑或过小的图像 MUST 视为屏幕录制权限失败，返回中文步骤，且 MUST NOT 把空图发给模型。默认 MUST 在图上标注当前光标位置。成功截图 MUST 更新后续鼠标工具使用的视图坐标系，且该坐标系 MUST 写入当前会话，以便后续用户回合与进程重启后恢复。给定 `region` 时 MUST 先将原点与宽高夹紧到主屏逻辑范围内，摘要与视图帧的逻辑宽高 MUST 使用夹紧后的值，MUST NOT 把超出主屏的请求宽高写入坐标系。

#### Scenario: 全屏截图成功

- **WHEN** 模型调用 `screenshot` 且屏幕录制已授权
- **THEN** 工具写入 PNG，摘要包含 `path`、逻辑宽高、`view_width`、`view_height`、`origin`、`scale`、`cursor`、`coordinate_space`，并附带该图像引用

#### Scenario: 摘要光标使用视图像素

- **WHEN** 全屏截图的逻辑尺寸为 1920×1080、视图为 1536×864，光标逻辑坐标为 (1282, 834)
- **THEN** 摘要 `cursor` 为换算后的视图像素 (约 1026, 667)，且 `y` 不超过 `view_height`

#### Scenario: 未授权得到黑图

- **WHEN** 截图结果全黑或尺寸过小
- **THEN** 工具返回屏幕录制授权的中文步骤，且不把该图作为模型输入

#### Scenario: 超界区域按主屏夹紧

- **WHEN** 主屏逻辑尺寸为 1920×1080，模型调用 `screenshot` 且 `region` 为 `(0, 0, 2560, 1440)`
- **THEN** 视图帧逻辑宽高为 1920×1080，MUST NOT 把 2560 或 1440 写入坐标系

### Requirement: 查询屏幕与指针

`screen_info` MUST 返回主屏逻辑分辨率、`scale` 与当前鼠标逻辑坐标。MUST NOT 要求确认。

#### Scenario: 读取屏幕信息

- **WHEN** 模型调用 `screen_info`
- **THEN** 结果包含 `screen_width`、`screen_height`、`scale`、`mouse_x`、`mouse_y`

### Requirement: 逻辑坐标移动指针

`mouse_move` MUST 将输入的视图像素换算为逻辑像素后移动指针。有视图帧时，输入 MUST 先满足当前视图边界；换算后若逻辑坐标超出主屏，MUST 夹紧到主屏内并在结果中说明。MUST NOT 要求确认。可选 `target_id` 命中最近一次 `ocr_locate` 结果时，MUST 改用该项逻辑中心。移动成功后 MUST 再截取当前画面（含光标标注），按 `screenshot` 规则落盘、更新视图坐标系，并把该 PNG 作为同一条工具结果回注。

#### Scenario: 移动到可见点

- **WHEN** 模型调用 `mouse_move`，换算后的逻辑坐标在主屏内
- **THEN** 指针移动到该逻辑坐标，且工具结果含新截图图像引用

#### Scenario: 越界夹紧

- **WHEN** 模型调用 `mouse_move`，输入落在当前视图内，但换算后的 `x` 或 `y` 超出主屏
- **THEN** 指针移到夹紧后的位置，结果说明发生了夹紧，且仍附新截图

### Requirement: 点击与拖拽需确认

`mouse_click` MUST 支持左/右/中键与单击/双击，MUST 只点击当前指针，MUST NOT 要求确认。`mouse_drag` MUST 从当前指针拖到视图像素 `(x2, y2)`，MUST NOT 要求确认。二者 MUST 要求本会话在上次点击/拖拽之后已经成功 `mouse_move` 放过光标，且最近一次光标截图来自 `mouse_move` 或其后的 `screenshot`。从未 `mouse_move`、或点击之后尚未再次 `mouse_move` 时 MUST 拒绝，并要求先移鼠看图。

#### Scenario: 当前位置单击

- **WHEN** 最近一次成功工具为 `mouse_move`，模型调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击左键，不弹出确认

#### Scenario: move 后再截图仍可点击

- **WHEN** 模型先成功 `mouse_move`，再成功 `screenshot`，然后调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击，MUST NOT 因最近一帧是 `screenshot` 而拒绝

#### Scenario: 未先移鼠则拒绝拖拽

- **WHEN** 本会话尚未成功 `mouse_move`，模型调用 `mouse_drag`
- **THEN** 不移动指针、不按下鼠标，工具结果为错误，文案要求先 `mouse_move`

### Requirement: 滚轮滚动

系统 MUST 提供 `mouse_scroll`。该工具 MUST 接受整数 `clicks`（正数向上、负数向下），可选视图像素 `x`/`y`；给出坐标时 MUST 先换算为逻辑像素并移动，再滚动。MUST NOT 要求确认。MUST NOT 提供横向滚动。

#### Scenario: 在指定点向上滚动

- **WHEN** 模型调用 `mouse_scroll`，`clicks` 为正，并给出最近一次截图视图内的 `x`、`y`
- **THEN** 指针先移到换算后的逻辑坐标，再向上滚动相应格数，且不弹出确认

#### Scenario: 无坐标滚动当前位置

- **WHEN** 模型调用 `mouse_scroll` 且只给 `clicks`
- **THEN** 不先移动，按当前指针位置滚动

### Requirement: 视图像素换算为逻辑像素

`mouse_move`、`mouse_drag`、`mouse_scroll` 的坐标输入 MUST 解释为最近一次成功截图回注给主模型的那张图上的像素。工具 MUST 按该图的视图宽高、逻辑宽高与区域原点换算成逻辑像素，再交给桌面后端。有视图帧时，输入超出该图像素范围 MUST 拒绝执行，而不是夹紧后执行。换算后的逻辑坐标超出主屏时 MUST 夹紧到主屏内并在结果中说明。当前会话尚无成功截图时，输入 MUST 当作逻辑像素，并在结果中说明未做视图换算。该坐标系 MUST 在同一会话的后续用户回合中仍然有效，不得因 TUI worker 结束而丢失。进程内读取当前帧时 MUST 以按会话缓存的帧为准，MUST NOT 让已过期的 ContextVar 覆盖较新的缓存帧。

#### Scenario: 按视图像素移动

- **WHEN** 最近一次全屏截图的视图宽为逻辑宽的一半，模型调用 `mouse_move` 给出视图坐标 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`（在未夹紧的情况下）

#### Scenario: 区域截图后的局部坐标

- **WHEN** 最近一次截图 `region` 原点为逻辑 `(200, 100)`，视图与区域逻辑尺寸之比为 1，模型给出视图 `(10, 15)`
- **THEN** 后端收到的逻辑坐标为 `(210, 115)`

#### Scenario: 下一用户回合仍按视图像素换算

- **WHEN** 上一回合已成功全屏截图且视图宽为逻辑宽的一半，新回合在未再截图的情况下调用 `mouse_move` 给出视图 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`，结果说明已从视图像素换算，且 MUST NOT 写「尚无截图」

#### Scenario: 按定位编号移动

- **WHEN** 最近一次 `ocr_locate` 成功且含 `id=1`，模型调用 `mouse_move` 且 `target_id` 为 `1`
- **THEN** 指针移到该项的逻辑中心，不使用本次调用中的 `x`/`y`，并回注光标截图

#### Scenario: 后置全屏截图覆盖超界区域帧

- **WHEN** 先前 `screenshot` 误用大于主屏的 region 写入了错误逻辑尺寸，随后一次无 region 的成功截图使用主屏尺寸
- **THEN** 之后的 `mouse_move` MUST 按主屏逻辑尺寸换算，MUST NOT 继续使用超界宽高

### Requirement: 定位编号跨回合保留

成功的 `locate` MUST 把编号到逻辑中心的映射写入当前会话，且该映射 MUST 绑定生成它的当前截图坐标帧。后续用户回合在同一会话中按 `target_id` 移动时，只有尚未成功生成新截图且当前帧仍为该定位来源时才可命中；任何成功 `screenshot`（包括 `mouse_move` 或破坏性动作的后置截图）MUST 清空旧编号。会话 JSON 缺少该字段时 MUST 视为没有定位结果。

#### Scenario: 下一回合按未刷新帧编号移动

- **WHEN** 上一回合 `locate` 在当前截图上记下 `id=1` 的逻辑中心，且新回合开始前未成功生成新截图
- **THEN** 指针移到该逻辑中心，且 MUST NOT 报没有该编号

#### Scenario: 新截图后旧编号不可移动

- **WHEN** 当前帧的 `locate` 已生成 `id=1`，随后成功生成新的截图
- **THEN** 后续调用 `mouse_move(target_id=1)` 返回中文错误而不移动指针

### Requirement: 新截图使定位事实与编号同步失效

每次成功 `screenshot` 创建或覆盖当前 `ViewFrame` 时，系统 MUST 清空绑定旧帧的可执行 `locate_hits`，并使对应短期定位事实失效。仅当前活动 `ViewFrame.image_path` 上、`coordinate_space=view` 且非观察专用的 `locate` 结果可创建有效定位事实。历史图、带框副本、空结果或定位失败 MUST NOT 留下有效定位事实。

#### Scenario: 新截图后事实摘要不再提供旧编号

- **WHEN** 当前帧的 `locate` 已生成 `id=1`，随后成功生成新的截图
- **THEN** 模型事实摘要不再提供 `id=1`

#### Scenario: 观察专用定位不写入事实

- **WHEN** 模型对历史截图或带框副本调用 `locate`
- **THEN** 结果仍可供观察，但不会创建可执行定位事实或可供移动的编号

### Requirement: 桌面工具拒绝无当前坐标帧的定位编号

`mouse_move` 与支持 `target_id` 的 `mouse_scroll` MUST 只接受由当前会话当前截图坐标帧生成的定位编号。定位工具清空编号、当前截图刷新编号或会话中不存在有效编号时，桌面工具 MUST 返回中文错误，MUST NOT 移动、滚动或点击。该限制 MUST 不影响模型直接传入最近截图的视图像素坐标。

#### Scenario: 观察专用定位后拒绝编号

- **WHEN** 模型对非当前截图调用 `locate`，随后以返回的 `target_id` 调用 `mouse_move`
- **THEN** `mouse_move` 返回要求先对当前截图调用 `locate` 的中文错误，且桌面后端不接收移动操作

### Requirement: 输入文本与按键分离

`keyboard_type` MUST 只接受文本并写入当前前台窗口；MUST NOT 接受按键名。含非 ASCII 的文本 MUST 通过剪贴板粘贴，不得静默丢字。`keyboard_press.keys` MUST 只接受非空字符串数组；单键也必须使用单元素数组，例如 `["enter"]`，组合键必须使用数组，例如 `["command", "tab"]`。`keyboard_press` MUST NOT 接受自由文本、单个字符串或 JSON 数组文本形式的字符串。数组元素 MUST 是白名单键名；白名单外的键名 MUST 拒绝。关机或退出登录相关组合 MUST 拒绝。二者 MUST NOT 要求确认。本会话尚无成功的 `screenshot` 或 `mouse_move` 截图时，二者 MUST 拒绝执行并要求先截图或移鼠。

#### Scenario: 写入 ASCII 文本

- **WHEN** 已有光标截图，模型调用 `keyboard_type`，`text` 为 `1+1`
- **THEN** 该文本被输入到当前前台窗口，且不弹出确认

#### Scenario: 按下回车

- **WHEN** 已有光标截图，模型调用 `keyboard_press`，`keys` 为 `["enter"]`
- **THEN** 系统按下回车，且不把 `enter` 当作普通文本写入

#### Scenario: 按下组合键

- **WHEN** 已有光标截图，模型调用 `keyboard_press`，`keys` 为 `["command", "tab"]`
- **THEN** 系统将 `command` 与 `tab` 作为一个组合键发送

#### Scenario: 拒绝非数组格式

- **WHEN** 模型调用 `keyboard_press`，`keys` 为 `command+tab` 或 `["command", "tab"]` 的字符串表示
- **THEN** 工具返回要求使用非空字符串数组的错误，且不发送按键

#### Scenario: 拒绝未知键名

- **WHEN** 模型调用 `keyboard_press`，`keys` 含白名单外的名称
- **THEN** 工具返回错误且不发送按键

#### Scenario: 拒绝危险热键

- **WHEN** 模型调用 `keyboard_press`，`keys` 为退出登录或关机相关组合
- **THEN** 工具返回错误且不发送按键

#### Scenario: 无截图则拒绝输入

- **WHEN** 本会话尚无成功截图，模型调用 `keyboard_type`
- **THEN** 不输入，工具结果为错误，文案要求先 `screenshot` 或 `mouse_move`

### Requirement: macOS 拒绝 windows 键

当运行平台为 macOS 时，`keyboard_press` 的 `keys` 若含 `windows` 或 `win`，MUST 返回中文错误，说明本机是 macOS、应使用 `command`，MUST NOT 发送按键。其他平台 MUST NOT 仅因键名为 `windows` 而套用本条。

#### Scenario: macOS 上拒绝 Win+R

- **WHEN** 运行在 macOS，已有截图，模型调用 `keyboard_press`，`keys` 为 `["windows", "r"]`
- **THEN** 不按键，工具结果含「macOS」与「command」

### Requirement: 桌面调用不阻塞界面

桌面后端的同步调用 MUST 在工作线程中执行。生产实现 MUST 开启 failsafe，并在连续动作之间加入短暂暂停。测试 MUST 注入假后端，MUST NOT 在 CI 中驱动真实鼠标、键盘或屏幕。

#### Scenario: 假后端记录点击

- **WHEN** 测试用假后端调用 `mouse_click`
- **THEN** 后端记录调用参数，真实指针位置不变

### Requirement: 权限失败对用户可读

屏幕录制或辅助功能缺失时，工具 MUST 返回可照做的中文步骤（系统设置中的屏幕录制 / 辅助功能，勾选运行本程序的终端）。MUST NOT 只抛出未翻译的英文异常。

#### Scenario: 辅助功能未授权

- **WHEN** 键鼠 API 因辅助功能权限失败
- **THEN** 工具结果包含中文授权步骤，图继续进入 `think`

### Requirement: 变异动作成功后附新截图

`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 在桌面后端执行成功后，MUST 再截取当前画面，按既有 `screenshot` 规则落盘、更新视图坐标系，并把该 PNG 作为同一条工具结果的图像回注。结果文本 MUST 仍包含原动作摘要，且 MUST 包含新截图的路径与视图尺寸信息。动作失败或权限错误时 MUST NOT 追加截图，MUST NOT 用空图或黑图更新坐标系。`mouse_move` MUST 在移动成功后附带截图（见「逻辑坐标移动指针」）。`screen_info` MUST NOT 因此附带截图。后置截图失败（全黑或过小）时 MUST 保留动作摘要与中文权限说明，MUST NOT 把该空图发给模型。

#### Scenario: 单击成功带回新图

- **WHEN** 无坐标的 `mouse_click` 且后端点击成功
- **THEN** 该次工具结果含新 PNG 引用，摘要含新图路径，且会话视图坐标系更新为该图

#### Scenario: 移动指针附截图

- **WHEN** 模型调用 `mouse_move` 且移动成功
- **THEN** 工具结果含新截图图像引用，图上标注当前光标

### Requirement: 视图像素必须落在当前视图内

当会话已有成功截图的视图帧，且鼠标工具使用 `x`/`y`（而非 `target_id`）时，输入坐标 MUST 满足 `0 ≤ x < view_width` 且 `0 ≤ y < view_height`。任一端出界时 MUST 返回中文错误，错误中 MUST 包含给出的坐标与当前视图宽高，MUST NOT 移动指针、点击、拖拽或滚动，MUST NOT 将坐标夹紧到屏幕边缘后当作成功。`mouse_drag` 的终点 MUST 通过该校验。使用 `target_id` 时 MUST NOT 套用本条视图边界，改为使用定位表中的逻辑中心。尚无视图帧时 MUST NOT 套用本条，输入仍按逻辑像素处理。

#### Scenario: 视图高度外的移动被拒绝

- **WHEN** 最近一次截图视图为 1536×864，模型调用 `mouse_move` 且参数为 `(710, 950)`
- **THEN** 不移动，工具结果为错误，文案含 `950` 与 `864`

#### Scenario: 拖拽终点出界则整次拒绝

- **WHEN** 最近一次截图视图为 1536×864，已通过 `mouse_move` 验证光标，模型调用 `mouse_drag`，终点 `y` 大于等于 864
- **THEN** 不拖拽，工具结果为错误

#### Scenario: 定位编号不受视图边界限制

- **WHEN** 最近一次 `ocr_locate` 含 `id=1`，模型调用 `mouse_move` 且 `target_id` 为 `1`
- **THEN** 按该项逻辑中心移动并回注截图，即使该中心换算回视图后贴近边缘

### Requirement: 动作摘要只报告视图像素

在已有视图帧时，`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll` 成功后的模型可见摘要 MUST 使用实际落点对应的视图像素，MUST NOT 写出逻辑分辨率下的坐标数字。若换算后因取整超出主屏而夹紧，摘要 MUST 说明发生了夹紧。后置截图 JSON 的 `cursor` 与 `coordinate_space` MUST 仍为视图像素。尚无视图帧时摘要可报告逻辑像素，且 MUST 说明未做视图换算。

#### Scenario: 移动摘要不含逻辑坐标

- **WHEN** 最近一次全屏截图视图宽为逻辑宽的一半，模型调用 `mouse_move` 给出视图 `(100, 40)` 且未夹紧
- **THEN** 摘要含视图像素 `(100, 40)` 或与之等价的实际落点视图坐标，且 MUST NOT 把逻辑 `(200, 80)` 写进摘要

### Requirement: 坐标桌面工具作为视觉后备

当当前 UI 快照的元素 backend 为 `vision`，或结构化浏览器／AX 后端明确不可用且存在当前帧视觉目标时，系统 MUST 使用既有 `ViewFrame`、移鼠、光标截图与坐标换算规则执行坐标后备。Browser 或 AX 元素存在有效结构化 locator 时，系统 MUST NOT 因默认策略而改用坐标桌面工具。

#### Scenario: 结构化按钮不触发鼠标后备
- **WHEN** 当前有效元素为可点击的 `browser` 或 `macos_ax` 元素
- **THEN** 语义点击不调用 `mouse_move` 或 `mouse_click`

#### Scenario: 自绘界面使用视觉后备
- **WHEN** 当前界面没有可用 DOM／AX 元素，但视觉快照提供当前帧目标
- **THEN** 系统通过现有移鼠和截图核验链路执行坐标动作

### Requirement: 语义定位候选复用既有移动核验

来自语义视觉定位或 macOS Dock 发现的候选 MUST 仅在绑定当前活动 `ViewFrame` 时写入定位表。`mouse_move` 使用该编号后 MUST 继续回注光标截图；语义名称不得替代移动、后置截图或无坐标点击门禁。

#### Scenario: Chrome 语义候选移动后仍核验
- **WHEN** 当前帧中的 Chrome 语义候选被用于 `mouse_move(target_id=...)`
- **THEN** 系统移动鼠标并返回含光标的新截图，尚未自动点击 Chrome

### Requirement: 桌面工具保持状态层安全边界
桌面工具 MAY 读取当前帧绑定的桌面状态快照以生成中文诊断或动作后预期验证所需的观察信息，但 MUST NOT 依赖快照绕过现有截图、坐标换算、定位编号、移鼠后截图或无坐标点击门禁。前台窗口、焦点元素或活动对话框为未知时，工具 MUST 保持既有安全行为，不得臆测目标或静默改变输入目的地。

#### Scenario: 未知前台窗口不放宽输入门禁
- **WHEN** 当前状态快照无法确定前台窗口，模型请求 `keyboard_type` 或 `keyboard_press`
- **THEN** 工具仍按既有截图与光标核验规则执行或拒绝，并在结果中说明前台窗口状态未知

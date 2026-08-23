## ADDED Requirements

### Requirement: 新画面清空定位表

模型直接调用的成功 `screenshot`，以及点击、拖拽、滚动、输入、按键成功后的后置截图，MUST 清空当前会话的定位编号表并写入会话。`mouse_move` 成功后的光标核验截图 MUST NOT 清空该表。清空后按 `target_id` 移动 MUST 报没有该编号，直到下一次成功 `locate`。

#### Scenario: 截图后旧编号失效

- **WHEN** 会话已有 `id=1` 的定位中心，模型随后成功调用 `screenshot`
- **THEN** 再调用 `mouse_move` 且 `target_id` 为 `1` 时工具返回没有该编号的错误

#### Scenario: 移鼠核验截图保留编号

- **WHEN** 会话已有 `id=1` 的定位中心，模型调用 `mouse_move` 且 `target_id` 为 `1` 并成功回注光标截图
- **THEN** 随后再次按 `target_id` 为 `1` 移动仍命中同一逻辑中心

## MODIFIED Requirements

### Requirement: 逻辑坐标移动指针

`mouse_move` MUST 将输入的视图像素换算为逻辑像素后移动指针。有视图帧时，输入 MUST 先满足当前视图边界；换算后若逻辑坐标超出主屏，MUST 夹紧到主屏内并在结果中说明。MUST NOT 要求确认。可选 `target_id` 命中最近一次 `locate` 结果时，MUST 改用该项逻辑中心。MUST NOT 因存在定位表而拒绝裸 `x`/`y`。移动成功后 MUST 再截取当前画面（含光标标注），按 `screenshot` 规则落盘、更新视图坐标系，并把该 PNG 作为同一条工具结果回注。

#### Scenario: 移动到可见点

- **WHEN** 模型调用 `mouse_move`，换算后的逻辑坐标在主屏内
- **THEN** 指针移动到该逻辑坐标，且工具结果含新截图图像引用

#### Scenario: 越界夹紧

- **WHEN** 模型调用 `mouse_move`，输入落在当前视图内，但换算后的 `x` 或 `y` 超出主屏
- **THEN** 指针移到夹紧后的位置，结果说明发生了夹紧，且仍附新截图

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

- **WHEN** 最近一次 `locate` 成功且含 `id=1`，模型调用 `mouse_move` 且 `target_id` 为 `1`
- **THEN** 指针移到该项的逻辑中心，不使用本次调用中的 `x`/`y`，并回注光标截图

#### Scenario: 后置全屏截图覆盖超界区域帧

- **WHEN** 先前 `screenshot` 误用大于主屏的 region 写入了错误逻辑尺寸，随后一次无 region 的成功截图使用主屏尺寸
- **THEN** 之后的 `mouse_move` MUST 按主屏逻辑尺寸换算，MUST NOT 继续使用超界宽高

### Requirement: 定位编号跨回合保留

成功的 `locate` MUST 把编号到逻辑中心的映射写入当前会话。后续用户回合在同一会话中按 `target_id` 移动时 MUST 仍能命中，直到下一次成功定位覆盖，或被新画面截图清空。会话 JSON 缺少该字段时 MUST 视为没有定位结果。

#### Scenario: 下一回合按编号移动

- **WHEN** 上一回合 `locate` 记下 `id=1` 的逻辑中心，新回合调用 `mouse_move` 且 `target_id` 为 `1`
- **THEN** 指针移到该逻辑中心，且 MUST NOT 报没有该编号

### Requirement: 视图像素必须落在当前视图内

当会话已有成功截图的视图帧，且鼠标工具使用 `x`/`y`（而非 `target_id`）时，输入坐标 MUST 满足 `0 ≤ x < view_width` 且 `0 ≤ y < view_height`。任一端出界时 MUST 返回中文错误，错误中 MUST 包含给出的坐标与当前视图宽高，MUST NOT 移动指针、点击、拖拽或滚动，MUST NOT 将坐标夹紧到屏幕边缘后当作成功。`mouse_drag` 的终点 MUST 通过该校验。使用 `target_id` 时 MUST NOT 套用本条视图边界，改为使用定位表中的逻辑中心。尚无视图帧时 MUST NOT 套用本条，输入仍按逻辑像素处理。

#### Scenario: 视图高度外的移动被拒绝

- **WHEN** 最近一次截图视图为 1536×864，模型调用 `mouse_move` 且参数为 `(710, 950)`
- **THEN** 不移动，工具结果为错误，文案含 `950` 与 `864`

#### Scenario: 拖拽终点出界则整次拒绝

- **WHEN** 最近一次截图视图为 1536×864，已通过 `mouse_move` 验证光标，模型调用 `mouse_drag`，终点 `y` 大于等于 864
- **THEN** 不拖拽，工具结果为错误

#### Scenario: 定位编号不受视图边界限制

- **WHEN** 最近一次 `locate` 含 `id=1`，模型调用 `mouse_move` 且 `target_id` 为 `1`
- **THEN** 按该项逻辑中心移动并回注截图，即使该中心换算回视图后贴近边缘

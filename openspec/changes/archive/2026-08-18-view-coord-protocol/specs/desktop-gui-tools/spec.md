## ADDED Requirements

### Requirement: 视图像素必须落在当前视图内

当会话已有成功截图的视图帧，且鼠标工具使用 `x`/`y`（而非 `target_id`）时，输入坐标 MUST 满足 `0 ≤ x < view_width` 且 `0 ≤ y < view_height`。任一端出界时 MUST 返回中文错误，错误中 MUST 包含给出的坐标与当前视图宽高，MUST NOT 移动指针、点击、拖拽或滚动，MUST NOT 将坐标夹紧到屏幕边缘后当作成功。`mouse_drag` 的起点与终点 MUST 都通过该校验。使用 `target_id` 时 MUST NOT 套用本条视图边界，改为使用定位表中的逻辑中心。尚无视图帧时 MUST NOT 套用本条，输入仍按逻辑像素处理。

#### Scenario: 视图高度外的点击被拒绝

- **WHEN** 最近一次截图视图为 1536×864，用户批准 `mouse_click` 且参数为 `(710, 950)`
- **THEN** 不点击，工具结果为错误，文案含 `950` 与 `864`

#### Scenario: 拖拽终点出界则整次拒绝

- **WHEN** 最近一次截图视图为 1536×864，用户批准 `mouse_drag`，起点在视图内、终点 `y` 大于等于 864
- **THEN** 不拖拽，工具结果为错误

#### Scenario: 定位编号不受视图边界限制

- **WHEN** 最近一次 `ocr_locate` 含 `id=1`，用户批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 按该项逻辑中心点击，即使该中心换算回视图后贴近边缘

### Requirement: 动作摘要只报告视图像素

在已有视图帧时，`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll` 成功后的模型可见摘要 MUST 使用实际落点对应的视图像素，MUST NOT 写出逻辑分辨率下的坐标数字。若换算后因取整超出主屏而夹紧，摘要 MUST 说明发生了夹紧。后置截图 JSON 的 `cursor` 与 `coordinate_space` MUST 仍为视图像素。尚无视图帧时摘要可报告逻辑像素，且 MUST 说明未做视图换算。

#### Scenario: 点击摘要不含逻辑坐标

- **WHEN** 最近一次全屏截图视图宽为逻辑宽的一半，用户批准 `mouse_click` 给出视图 `(100, 40)` 且未夹紧
- **THEN** 摘要含视图像素 `(100, 40)` 或与之等价的实际落点视图坐标，且 MUST NOT 把逻辑 `(200, 80)` 写进摘要

## MODIFIED Requirements

### Requirement: 逻辑坐标移动指针

`mouse_move` MUST 将输入的视图像素换算为逻辑像素后移动指针。有视图帧时，输入 MUST 先满足当前视图边界；换算后若逻辑坐标超出主屏，MUST 夹紧到主屏内并在结果中说明。MUST NOT 要求确认。可选 `target_id` 命中最近一次 `ocr_locate` 结果时，MUST 改用该项逻辑中心。

#### Scenario: 移动到可见点

- **WHEN** 模型调用 `mouse_move`，换算后的逻辑坐标在主屏内
- **THEN** 指针移动到该逻辑坐标

#### Scenario: 越界夹紧

- **WHEN** 模型调用 `mouse_move`，输入落在当前视图内，但换算后的 `x` 或 `y` 超出主屏
- **THEN** 指针移到夹紧后的位置，结果说明发生了夹紧

### Requirement: 视图像素换算为逻辑像素

`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll` 的坐标输入 MUST 解释为最近一次成功 `screenshot` 回注给主模型的那张图上的像素。工具 MUST 按该图的视图宽高、逻辑宽高与区域原点换算成逻辑像素，再交给桌面后端。有视图帧时，输入超出该图像素范围 MUST 拒绝执行，而不是夹紧后执行。换算后的逻辑坐标超出主屏时 MUST 夹紧到主屏内并在结果中说明。当前会话尚无成功截图时，输入 MUST 当作逻辑像素，并在结果中说明未做视图换算。该坐标系 MUST 在同一会话的后续用户回合中仍然有效，不得因 TUI worker 结束而丢失。

#### Scenario: 按视图像素点击

- **WHEN** 最近一次全屏截图的视图宽为逻辑宽的一半，模型批准后的 `mouse_click` 给出视图坐标 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`（在未夹紧的情况下）

#### Scenario: 区域截图后的局部坐标

- **WHEN** 最近一次截图 `region` 原点为逻辑 `(200, 100)`，视图与区域逻辑尺寸之比为 1，模型给出视图 `(10, 15)`
- **THEN** 后端收到的逻辑坐标为 `(210, 115)`

#### Scenario: 下一用户回合仍按视图像素换算

- **WHEN** 上一回合已成功全屏截图且视图宽为逻辑宽的一半，新回合在未再截图的情况下调用 `mouse_move` 给出视图 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`，结果说明已从视图像素换算，且 MUST NOT 写「尚无截图」

#### Scenario: 按定位编号点击

- **WHEN** 最近一次 `ocr_locate` 成功且含 `id=1`，用户批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 指针移到该项的逻辑中心并点击，不使用本次调用中的 `x`/`y`

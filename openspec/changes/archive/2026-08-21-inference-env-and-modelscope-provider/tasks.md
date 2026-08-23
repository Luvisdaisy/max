## 1. 依赖与 .env 骨架

- [x] 1.1 增加 `python-dotenv`；`.gitignore` 加入 `.env`；提交无密钥 `.env.example`（含 `MAX_PROVIDER` / `MAX_PROVIDER_KEY` / `MODEL_NAME` 与既有 `MAX_GUI_*` 可调字段）
- [x] 1.2 若 `modelscope` 仅被下载路径引用，从 `pyproject.toml` 移除该依赖并更新锁文件

## 2. 配置加载

- [x] 2.1 `detect_project_root` 之后载入根目录 `.env`（`override=False`）；无文件不失败
- [x] 2.2 `Settings` 增加 `provider` 与原文 `MODEL_NAME`；删除 `MODEL_ALIASES` / `resolve_model_alias` / `MODELSCOPE_IDS` / `download_command`
- [x] 2.3 解析 `MAX_PROVIDER`（仅 `local`|`modelscope`）、`MAX_PROVIDER_KEY`、`MODEL_NAME` 缺省（local=`qwen3.5-4b`，modelscope=`Qwen/Qwen3.8-27B`）；不认 `MODELSCOPE_SDK_TOKEN`；非法 provider 中文失败
- [x] 2.4 补测试：`.env` 载入、进程环境优先、两套缺省模型名、非法 provider、仅 SDK Token 视为缺 key

## 3. 客户端与生命周期

- [x] 3.1 `local` 仍按 `model/<MODEL_NAME>` 检查权重，缺权重只报路径、不提 download；`modelscope` 跳过权重、`base_url` 固定魔搭、`model` 发 `MODEL_NAME` 原文
- [x] 3.2 `modelscope` 缺 key 或连接失败的中文错误不得包含 `max-gui serve`；两种后端请求均带 `tools` 与 `tool_choice=auto`
- [x] 3.3 删除 `download_model` 与 CLI `download` / `--model`；`serve` 仅 `local`，`modelscope` 下非零退出并提示改 `.env`
- [x] 3.4 补测试：local 短名 `4b` 不映射；modelscope 无本地目录仍发请求；mock 魔搭 SSE `tool_calls` 拼装；`max-gui download` 不再是受支持入口；serve 在 modelscope 下失败

## 4. TUI 与会话

- [x] 4.1 删除 `/model` 处理与帮助文案；`/model` 走未知命令
- [x] 4.2 创建会话仍写入当前 `MODEL_NAME`；`/sessions` 切换不 `with_model`、不改 provider
- [x] 4.3 补 TUI / 会话测试：`/model` 报未知；切换旧会话后 think 仍用配置模型名

## 5. 文档与收尾

- [x] 5.1 更新 `README.md`：复制 `.env.example`、本地放权重、云端填 key、去掉 download 与 `/model` 说明
- [x] 5.2 `uv run ruff format src tests` 与 `uv run ruff check src tests`；相关测试通过

## ADDED Requirements

### Requirement: OmniParser 路径 worker 必须为同机地址

当 OmniParser worker 协议使用主进程本地绝对图像路径时，`MAX_GUI_OMNIPARSER_BASE_URL` 的 host MUST 为 loopback 地址。配置为非 loopback 地址时，首次 `locate` MUST 返回中文配置错误，MUST NOT 将本地绝对路径发送到该地址，也 MUST NOT 启动新的 worker。

#### Scenario: 拒绝远端路径 worker

- **WHEN** `MAX_GUI_OMNIPARSER_BASE_URL` 配置为 `http://192.0.2.10:8002`
- **THEN** `locate` 返回说明仅支持本机 worker 的中文错误，且不会发出 HTTP 请求

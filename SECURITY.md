# 安全策略 · Security Policy

## 支持范围

本项目是本地优先的单机工程：macOS 宿主应用 + 同机独立 Local Engine Service + 本地 SQLite 数据内核，默认不暴露公网服务。安全修复只针对 `main` 分支的最新状态。

## 报告漏洞

请**不要**在公开 issue、讨论区或 PR 中披露漏洞细节、利用代码、真实凭证或个人数据。

优先使用 GitHub 的私密漏洞报告入口（仓库 **Security → Report a vulnerability**）；若该入口不可用，请通过仓库维护者（GitHub [@hrygo](https://github.com/hrygo)）的私信渠道联系，并说明影响版本与复现条件。

## 重点关注的风险面

| 面 | 说明 |
|---|---|
| 本地 IPC | UDS + NDJSON 帧解析、长度前缀边界、消息校验与权限 |
| 数据写路径 | 唯一写入口是 Domain Engine 的 COMMIT；任何绕过 Proposal 校验的路径都是高危问题 |
| 知识越界 | `Character Reasoner` 收到超出角色已知边界的信息属于严重设计违例（不变量 6） |
| 外部模型与语音服务 | AgentScope 适配层、SpeechRail / OpenAI 兼容端点的凭证与数据出境范围 |
| 依赖与供应链 | Python（`engine/uv.lock`）与 GitHub Actions 的版本固定与自动追踪 |

## 凭证处理

- 凭证优先存放于系统钥匙串，绝不写入仓库、配置文件、Issue 或 PR；
- 仓库已启用 Dependabot 告警与安全更新、Actions 默认只读令牌权限（`contents: read`）、工作流显式超时熔断；
- 如发现已泄漏的凭证，请先告知维护者轮换，再讨论披露时间线。

## 不在范围内

- 依赖上游（AgentScope、`uv`、Xcode / macOS）自身的漏洞，请报告给对应上游；
- 在本机已获得完全控制权后，进一步读取用户自己的本地文件——这属于本地信任边界之内的行为。

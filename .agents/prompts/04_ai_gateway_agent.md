# Role: AGT-AI (Mystic Gateway / AI 运行时 Agent)

## 1. 角色使命
你是《诡秘世界》大模型与 AgentScope 2.0.8 运行时的安全隔离网关。
你负责 Mysterious AI Gateway 封装、Advice Interpreter、Character Reasoner、Story Director 熔断机制与结构化 Proposal 校验。

## 2. 授权目录与文件
- `engine/ai/`
- `engine/tests/test_ai_*.py`

## 3. 严格禁止行为 (Invariants 5, 7, 8)
- **绝对严禁** 为任何 Agent 或大模型挂载具备数据库写入能力的 Tool（不变量 5）。
- **绝对严禁** 让 AgentScope Runtime Memory 充当领域事实源（不变量 8）。
- **绝对严禁** 绕过 Context Compiler 直接向大模型喂入全量数据库内容。

## 4. 必备验证命令
```bash
python3 scripts/check_architecture_fitness.py
uv run pytest tests/ -k "ai or gateway or proposal"
```

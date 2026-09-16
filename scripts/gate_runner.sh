#!/usr/bin/env bash
# ==============================================================================
# 《诡秘世界》受保护门禁启动器 (HACF 2.1)
#
# 用法:
#   bash scripts/gate_runner.sh              # 默认 FULL_P0
#   bash scripts/gate_runner.sh DOMAIN_P0    # 角色专精档案
#
# 设计要点:
#   - 真实验收命令定义于受保护的 .hacf/gates/*.json，并由 registry.json 记录摘要；
#     本脚本不内嵌命令，避免「门禁可被任务自行改写」。
#   - 存在 .hacf/workspace.json（worktree 资源租约）时自动采用其 TMPDIR / SPM scratch /
#     端口段等运行时隔离参数。
# ==============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-FULL_P0}"

# 向后兼容：v1.0 文档/钩子中的 `--all-p0` 之类旧参数不再表示任意命令，统一回退到全量档案
case "${PROFILE}" in
    --*)
        echo "⚠️  旧参数 '${PROFILE}' 已废弃（门禁档案改为受保护引用），回退为 FULL_P0。"
        PROFILE="FULL_P0"
        ;;
esac

echo "=================================================================="
echo "️  [World of Mysteries] Protected Gate Runner · profile=${PROFILE}"
echo "=================================================================="

python3 "${REPO_ROOT}/scripts/gate_profile.py" run \
    --profile "${PROFILE}" \
    --cwd "${REPO_ROOT}" \
    --use-workspace-lease

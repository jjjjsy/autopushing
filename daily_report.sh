#!/bin/bash
# ============================================================
# 每日全球市场与光电半导体情报 - 自动化脚本
# ============================================================
# 用法:
#   ./daily_report.sh                    # 发送今天的日报（自动采集）
#   ./daily_report.sh --dry-run          # 仅生成HTML预览
#   ./daily_report.sh -d data.json       # 从JSON数据文件发送
#
# Cron 配置:
#   30 8 * * 1-5 /workspace/daily_report.sh >> /workspace/logs/cron.log 2>&1
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/daily_report_$(date +%Y%m%d).log"

# 确保 cron 服务运行（沙箱恢复后自动重启）
service cron start 2>/dev/null || true

# 确保日志目录存在
mkdir -p "${LOG_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# ============================================================
# 参数解析
# ============================================================
DRY_RUN=false
DATA_FILE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -d|--data-file)
            DATA_FILE="$2"
            shift 2
            ;;
        -o|--output)
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# ============================================================
# 执行
# ============================================================
log "=========================================="
log "日报推送系统启动"
log "Dry run: ${DRY_RUN}"
log "数据文件: ${DATA_FILE:-自动采集}"
log "=========================================="

# 触发 GitHub Actions（云端数据采集，确保即使本地失败也有备份）
log "触发 GitHub Actions..."
GH_TOKEN="${GH_TOKEN:-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}"
export GH_TOKEN
if gh workflow run daily-report.yml -R jjjjsy/autopushing 2>/dev/null; then
    log "  GHA 触发成功"
else
    log "  GHA 触发失败（可忽略，本地模式继续）"
fi

# 构建命令
CMD="python3 ${SCRIPT_DIR}/daily_report_auto.py"

if [ -n "${DATA_FILE}" ]; then
    CMD="${CMD} --data-file ${DATA_FILE}"
fi

if [ "${DRY_RUN}" = true ]; then
    CMD="${CMD} --dry-run"
fi

if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
    CMD="${CMD} ${EXTRA_ARGS[*]}"
fi

log "执行命令: ${CMD}"

if eval "${CMD}" 2>&1 | tee -a "${LOG_FILE}"; then
    log "日报推送成功"
    exit 0
else
    log "日报推送失败 (exit code: $?)"
    exit 1
fi

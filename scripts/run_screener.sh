#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# NASDAQ 보물주 스크리너 — 자동 실행 & 배포 스크립트
# 하루 4회 cron에 의해 호출됨
# ─────────────────────────────────────────────────────────────────────────────

REPO="/Users/jaeseung/stock-screener"
PYTHON="/opt/homebrew/opt/python@3.11/bin/python3.11"
LOG="$REPO/logs/screener.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S KST')

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo " 실행: $TIMESTAMP" >> "$LOG"
echo "========================================" >> "$LOG"

cd "$REPO" || { echo "REPO 없음: $REPO" >> "$LOG"; exit 1; }

# 스크리너 실행
"$PYTHON" scripts/tsd/refresh_data.py >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 스크리너 완료 — GitHub 배포 중..." >> "$LOG"

    # git add + commit + push
    git add docs/data.json >> "$LOG" 2>&1
    git diff --cached --quiet && {
        echo "ℹ️  data.json 변경 없음, push 스킵" >> "$LOG"
        exit 0
    }
    git commit -m "auto: screener update $(date '+%Y-%m-%d %H:%M KST')" >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1

    if [ $? -eq 0 ]; then
        echo "🚀 배포 완료" >> "$LOG"
    else
        echo "❌ push 실패 (네트워크/인증 확인)" >> "$LOG"
    fi
else
    echo "❌ 스크리너 실패 (exit=$EXIT_CODE)" >> "$LOG"
fi

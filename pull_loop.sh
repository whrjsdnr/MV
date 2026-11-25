#!/bin/bash
# ~/MV/pull_loop.sh — 당기기 주기 실행기
# 사용법: nohup bash ~/MV/pull_loop.sh > /dev/null 2>&1 &
INTERVAL=1800   # 30분 (초)
LOG=~/MV/pull.log

echo "=== 루프 시작 $(date -Is) (간격 ${INTERVAL}s) ===" >> "$LOG"
while true; do
  echo "--- 실행 $(date -Is) ---" >> "$LOG"
  bash ~/MV/pull_realiad.sh >> "$LOG" 2>&1
  echo "--- 종료 $(date -Is) ---" >> "$LOG"
  sleep "$INTERVAL"
done
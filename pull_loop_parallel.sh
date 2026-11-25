#!/bin/bash
# pull_loop_parallel.sh — 병렬 풀 주기 실행기 (크런치용, 20분 간격)
INTERVAL=1200
LOG=~/MV/pull_parallel_loop.log
echo "=== 병렬 루프 시작 $(date -Is) (간격 ${INTERVAL}s) ===" >> "$LOG"
while true; do
  echo "--- 실행 $(date -Is) ---" >> "$LOG"
  bash ~/MV/pull_realiad_parallel.sh >> "$LOG" 2>&1
  echo "--- 종료 $(date -Is) ---" >> "$LOG"
  sleep "$INTERVAL"
done

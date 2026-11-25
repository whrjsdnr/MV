#!/usr/bin/env bash
# 모델 학습 Run을 세션 독립 백그라운드로 실행하고 rss_monitor를 병행 투입한다.
# 사용: launch_resume_run.sh <model_key> <config_path> <output_root> <max_hours> <log_path>
set -u
MODEL="$1"; CONFIG="$2"; OUT="$3"; HOURS="$4"; LOG="$5"
: "${MV_DATA_RELEASE:?MV_DATA_RELEASE required}"
: "${REALIAD_DATA_ROOT:?REALIAD_DATA_ROOT required}"
cd /home/geonug/MV
mkdir -p "$OUT"
setsid nohup uv run --offline python scripts/experiments/run_weekend.py \
  --models "$MODEL" --config "$CONFIG" --output-root "$OUT" --max-hours "$HOURS" \
  > "$LOG" 2>&1 &
RUNNER_PID=$!
RUN_DIR=""
for _ in $(seq 1 180); do
  RUN_DIR=$(grep -m1 '^Run: ' "$LOG" 2>/dev/null | sed 's/^Run: //')
  [ -n "$RUN_DIR" ] && break
  sleep 1
done
if [ -n "$RUN_DIR" ]; then
  setsid nohup uv run --offline python scripts/experiments/rss_monitor.py \
    --run-dir "$RUN_DIR" --job "$MODEL" --output "$RUN_DIR/rss_monitor.json" \
    > "$LOG.monitor" 2>&1 &
  echo "monitor started for $RUN_DIR" >> "$LOG"
else
  echo "WARN: run dir not found; monitor not started" >> "$LOG"
fi
wait "$RUNNER_PID"

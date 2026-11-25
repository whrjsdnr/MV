#!/bin/bash
# pull_realiad_final.sh — FINAL 회수 전용: 서버 삭제 절대 금지 (FINAL_READY 이후 읽기전용 모드)
# 정책: 전송 + 로컬 도착 확인만. 서버의 어떤 파일도 삭제하지 않는다.
set -u
SSHK="-i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967"
SRV="root@38.147.83.15"
DEST="$HOME/MV/real-iad-backup"
PAR=5
echo "=== [$(date -Is)] FINAL PULL (NO-DELETE MODE, P=$PAR) ==="
mkdir -p "$DEST/export" "$DEST/offload" "$DEST/final" "$DEST/.chunks"

# 1. export 전체 (삭제 없음)
PAIRS=$(ssh $SSHK $SRV 'for e in /workspace/real-iad/outputs/*/export; do
  [ -d "$e" ] || continue
  exp=$(basename $(dirname "$e"))
  subs=$(ls -d "$e"/*/ 2>/dev/null || true)
  if [ -n "$subs" ]; then for s in $subs; do echo "$exp|$(basename $s)"; done
  else echo "$exp|."; fi
done')
echo "[1] export 대상: $(echo "$PAIRS" | wc -l)쌍 (서버삭제 안함)"
sync_one() {
  pair=$1; exp=${pair%%|*}; sub=${pair#*|}
  rsync -az --partial -e "ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967" \
    "root@38.147.83.15:/workspace/real-iad/outputs/$exp/export/$sub/" \
    "$HOME/MV/real-iad-backup/export/$exp/$sub/" && echo "[1] $pair 동기화완료"
}
export -f sync_one 2>/dev/null || true
echo "$PAIRS" | xargs -P "$PAR" -I{} bash -c 'sync_one "$@"' _ {}

# 2. offload 큐 전체 (삭제 없음)
if rsync -az -e "ssh $SSHK" $SRV:/workspace/real-iad/outputs/offload_queue.txt "$DEST/offload_queue.txt" 2>/dev/null; then
  ssh $SSHK $SRV 'while read -r p h size; do [ -e "$p" ] && echo "$size ${p#/}"; done < /workspace/real-iad/outputs/offload_queue.txt' \
    | sort -rn > "$DEST/.chunks/sized_final.txt"
  TOTAL=$(wc -l < "$DEST/.chunks/sized_final.txt")
  echo "[2] 큐 ${TOTAL}개"
  rm -f "$DEST/.chunks"/chunk_f*
  i=0
  while read -r size rel; do
    c=$((i % PAR)); i=$((i+1)); echo "$rel" >> "$DEST/.chunks/chunk_f$c"
  done < "$DEST/.chunks/sized_final.txt"
  pids=()
  for c in $(seq 0 $((PAR-1))); do
    f="$DEST/.chunks/chunk_f$c"; [ -s "$f" ] || continue
    ( rsync -azR --partial --files-from="$f" -e "ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967" \
        "$SRV:/" "$DEST/offload/" 2> "$DEST/rsync_errors_final_$c.log" ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  MISSING=0
  while read -r size rel; do
    [ -e "$DEST/offload/$rel" ] || { MISSING=$((MISSING+1)); echo "미도착: $rel"; }
  done < "$DEST/.chunks/sized_final.txt"
  echo "[2] 큐 전송 완료, 미도착 $MISSING"
fi

# 3. 최종 산출물 우선 당기기
echo "[3] deliverable_final + FINAL_REPORT + FINAL_READY 당기기"
for target in "outputs/deliverable_final" "outputs/deliverable_final.tar.gz" "outputs/FINAL_REPORT.md" "outputs/FINAL_READY" "outputs/manifest.csv"; do
  rsync -azR --partial -e "ssh $SSHK" "$SRV:/workspace/real-iad/$target" "$DEST/final/" 2>/dev/null && echo "[3] $target 완료" || echo "[3] $target 없음(걸러짐)"
done

# 4. 검증: 서버 manifest 대조 (있으면)
if [ -f "$DEST/final/workspace/real-iad/outputs/manifest.csv" ]; then
  echo "[4] manifest.csv 기반 sha256 대조 시작"
  ( cd "$DEST/final" && awk -F, 'NR>1 {print $NF, $1}' workspace/real-iad/outputs/manifest.csv 2>/dev/null | head -20000 | sha256sum -c - 2>/dev/null | grep -c ': OK$' || true )
fi
echo "[5] 서버 디스크(참고): $(ssh $SSHK $SRV "df -h / | tail -1")"
echo "=== FINAL PULL 완료 (서버 삭제 0건) ==="

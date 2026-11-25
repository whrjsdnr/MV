#!/bin/bash
# pull_realiad_parallel.sh — 병렬 offload/export 풀 (디스크 크런치용)
# 순서: 큐(삭제로 디스크 회복) 먼저 → export 나중. rsync --timeout으로 교착 방지.
set -u
SSHK="-i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967"
SRV="root@38.147.83.15"
DEST="$HOME/MV/real-iad-backup"
PAR=6
RT="--timeout=300 --contimeout=30"
echo "=== [$(date -Is)] parallel pull start (P=$PAR, queue-first) ==="
mkdir -p "$DEST/export" "$DEST/offload" "$DEST/.chunks"

# ---------- 1. offload 큐 병렬 전송+삭제 (먼저: 디스크 회복이 우선) ----------
if rsync -az $RT -e "ssh $SSHK" $SRV:/workspace/real-iad/outputs/offload_queue.txt "$DEST/offload_queue.txt" 2>/dev/null; then
  ssh $SSHK $SRV 'while read -r p h size; do [ -e "$p" ] && echo "$size ${p#/}"; done < /workspace/real-iad/outputs/offload_queue.txt' \
    | sort -rn > "$DEST/.chunks/sized.txt"
  TOTAL=$(wc -l < "$DEST/.chunks/sized.txt")
  echo "[1] 큐 ${TOTAL}개 필터링됨"
  rm -f "$DEST/.chunks"/chunk_*
  i=0
  while read -r size rel; do
    c=$((i % PAR)); i=$((i+1)); echo "$rel" >> "$DEST/.chunks/chunk_$c"
  done < "$DEST/.chunks/sized.txt"
  pids=()
  for c in $(seq 0 $((PAR-1))); do
    f="$DEST/.chunks/chunk_$c"; [ -s "$f" ] || continue
    ( rsync -azR $RT --partial --files-from="$f" -e "ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967" \
        --info=progress2 "$SRV:/" "$DEST/offload/" 2> "$DEST/rsync_errors_$c.log" ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  DEL="$DEST/delete_list.txt"; : > "$DEL"
  while read -r size rel; do
    [ -e "$DEST/offload/$rel" ] && echo "/$rel" >> "$DEL"
  done < "$DEST/.chunks/sized.txt"
  NDEL=$(wc -l < "$DEL")
  if [ "$NDEL" -gt 0 ]; then
    { while read -r p; do printf 'rm -rf "%s"\n' "$p"; done < "$DEL"; } | ssh $SSHK $SRV bash
  fi
  echo "[1] 큐 완료: 삭제 $NDEL/$TOTAL"
else
  echo "[1] 큐 없음 - 스킵"
fi

# ---------- 2. export 병렬 동기화 (나중: 성장 중인 export는 검증 불일치 시 보류) ----------
PAIRS=$(ssh $SSHK $SRV 'for e in /workspace/real-iad/outputs/*/export; do
  [ -d "$e" ] || continue
  exp=$(basename $(dirname "$e"))
  subs=$(ls -d "$e"/*/ 2>/dev/null || true)
  if [ -n "$subs" ]; then for s in $subs; do echo "$exp|$(basename $s)"; done
  else echo "$exp|."; fi
done')
echo "[2] export 대상: $(echo "$PAIRS" | wc -l)쌍"
sync_one() {
  pair=$1; exp=${pair%%|*}; sub=${pair#*|}
  timeout 900 rsync -az $RT --partial -e "ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967" \
    "root@38.147.83.15:/workspace/real-iad/outputs/$exp/export/$sub/" \
    "$HOME/MV/real-iad-backup/export/$exp/$sub/" || { echo "[2] FAIL/시간초과 $pair"; return; }
  left=$(rsync -ainc --checksum $RT -e "ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967" \
    "root@38.147.83.15:/workspace/real-iad/outputs/$exp/export/$sub/" \
    "$HOME/MV/real-iad-backup/export/$exp/$sub/" | head -5)
  if [ -z "$left" ]; then
    ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -p 34967 root@38.147.83.15 \
      "find '/workspace/real-iad/outputs/$exp/export/$sub' -type f \( -name '*.pt' -o -name '*.npy' -o -name '*.pth' -o -name '*.pth.tar' \) -delete" \
      && echo "[2] $pair 검증일치->서버삭제"
  else
    echo "[2] $pair 검증불일치(삭제보류)"
  fi
}
export -f sync_one 2>/dev/null || true
echo "$PAIRS" | xargs -P "$PAR" -I{} bash -c 'sync_one "$@"' _ {}

echo "[3] 서버 디스크: $(ssh $SSHK $SRV "df -h / | tail -1")"
echo "=== [$(date -Is)] parallel pull end ==="

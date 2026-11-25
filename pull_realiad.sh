#!/bin/bash
# 사용법: bash ~/MV/pull_realiad.sh  (일괄 전송 버전)
SSH="ssh -i ~/.ssh/id_ed25519 -p 34967"
SRV="root@38.147.83.15"
DEST=~/MV/real-iad-backup
mkdir -p "$DEST/export" "$DEST/offload"

# 1. export 당기기 -> 체크섬 검증 -> 서버 대용량 파일만 삭제
EXPORT_PATHS=$($SSH $SRV "ls -d /workspace/real-iad/outputs/*/export 2>/dev/null")
if [ -z "$EXPORT_PATHS" ]; then
  M=$($SSH $SRV "find /workspace/real-iad/outputs -maxdepth 3 -name 'manifest.json' 2>/dev/null | head -1")
  [ -n "$M" ] && EXPORT_PATHS=$(dirname "$M")
fi
for p in $EXPORT_PATHS; do
  name=$(basename $(dirname "$p"))
  echo "[1] export 당기기: $p -> $DEST/export/$name/"
  rsync -az -e "$SSH" "$SRV:$p/" "$DEST/export/$name/"
  rc=$?
  if [ $rc -eq 24 ]; then
    echo "[1] export 갱신 중 경합, 한 번 재시도: $p"
    rsync -az -e "$SSH" "$SRV:$p/" "$DEST/export/$name/"
    rc=$?
  fi
  [ $rc -ne 0 ] && [ $rc -ne 24 ] && { echo "[1] 전송 실패: $p (삭제 안 함, rc=$rc)"; continue; }

  DIFF=$(rsync -ainc --checksum -e "$SSH" "$SRV:$p/" "$DEST/export/$name/" | head -5)
  if [ -z "$DIFF" ]; then
    $SSH $SRV "find '$p' -type f \( -name '*.pt' -o -name '*.npy' -o -name '*.pth' \) -delete"
    echo "[1] 검증 일치 -> 서버 대용량 파일 삭제 완료: $p"
  else
    echo "[1] 검증 불일치(삭제 안 함): $DIFF"
  fi
done

# 2. 오프로드 큐 당겨오기
rsync -az -e "$SSH" $SRV:/workspace/real-iad/outputs/offload_queue.txt "$DEST/" 2>/dev/null || { echo "[2] 큐 없음"; exit 0; }

# 3. 큐 일괄 전송 (SSH 총 3회): 서버 측 존재 필터 -> 전송 -> 삭제
QUEUE="$DEST/offload_queue.txt"
LIST="$DEST/queue_files.txt"

# 3-1. 서버에서 실제 존재하는 항목만 필터 (유령 항목 제거, SSH 1회)
$SSH $SRV 'while read -r p _ _; do [ -e "$p" ] && echo "$p"; done < /workspace/real-iad/outputs/offload_queue.txt' \
  | sed 's|^/||' > "$LIST"
TOTAL=$(wc -l < "$LIST")
echo "[3] 일괄 전송 시작: ${TOTAL}개 파일 (유령 항목 제외, 진행률 바가 움직이면 정상)"

# 3-2. 전송 (에러는 파일로, 진행률은 화면에)
rsync -azR --info=progress2 --files-from="$LIST" -e "$SSH" "$SRV:/" "$DEST/offload/" 2> "$DEST/rsync_errors.log" || true

# 3-3. 도착 확인된 것만 일괄 삭제 (SSH 1회)
DEL="$DEST/delete_list.txt"
: > "$DEL"
while read -r rel; do
  [ -e "$DEST/offload/$rel" ] && echo "/$rel" >> "$DEL"
done < "$LIST"

NDEL=$(wc -l < "$DEL")
if [ "$NDEL" -gt 0 ]; then
  { while read -r p; do printf 'rm -rf "%s"\n' "$p"; done < "$DEL"; } | $SSH $SRV bash
  echo "[3] 일괄 삭제 완료: ${NDEL}개"
fi
echo "[3] 미전송/잔재: $((TOTAL - NDEL))개 (다음 주기에 재시도, 에러 상세: $DEST/rsync_errors.log)"

# 4. 완료 보고 + 서버 디스크 확인
echo "[4] 서버 디스크:"
$SSH $SRV "df -h / | tail -1"
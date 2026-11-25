"""학습 worker의 RSS를 주기적으로 샘플링해 peak memory를 기록한다.

학습 로직·실행기를 변경하지 않는다. runner가 작성하는 worker_lease.json(active)에서
PID를 발견하면 해당 프로세스 트리의 RSS를 interval 초마다 합산해 기록한다.
attempt가 바뀌어도 같은 출력에 누적한다.

종료 조건: (a) 기록이 있고 활성 lease가 2회 연속 없음(정상 종료),
(b) lease는 있으나 트리가 3회 연속 죽어있음(비정상 잔여), (c) --max-runtime 초과.

사용: uv run --offline python scripts/experiments/rss_monitor.py --run-dir <RUN_DIR> --job <model_key> --output <json>
"""
import argparse
import json
import time
from pathlib import Path

import psutil


def active_leases(run_dir, job):
    for path in sorted(Path(run_dir).glob(f'{job}/attempt_*/worker_lease.json')):
        try:
            lease = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if lease.get('active'):
            yield lease


def tree_rss(pid):
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None
    total, alive = 0, False
    for proc in [root] + root.children(recursive=True):
        try:
            total += proc.memory_info().rss
            alive = True
        except psutil.NoSuchProcess:
            continue
    return total if alive else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--interval', type=float, default=5.0)
    parser.add_argument('--max-runtime', type=float, default=48 * 3600)
    args = parser.parse_args()
    peak, samples = 0, []
    start = time.time()
    grace_no_lease, grace_dead = 0, 0
    while True:
        if time.time() - start > args.max_runtime:
            break
        leases = list(active_leases(args.run_dir, args.job))
        any_live = False
        for lease in leases:
            rss = tree_rss(lease['pid'])
            if rss is not None:
                any_live = True
                peak = max(peak, rss)
                samples.append(dict(t=time.time(), pid=lease['pid'], rss_bytes=rss))
        if samples:
            if not leases:
                grace_no_lease += 1
                grace_dead = 0
                if grace_no_lease >= 2:
                    break
            elif not any_live:
                grace_dead += 1
                grace_no_lease = 0
                if grace_dead >= 3:
                    break
            else:
                grace_no_lease = grace_dead = 0
        time.sleep(args.interval)
    Path(args.output).write_text(json.dumps(dict(
        peak_rss_bytes=peak, peak_rss_gib=round(peak / 2**30, 3),
        samples=len(samples)), indent=1) + '\n')


if __name__ == '__main__':
    main()

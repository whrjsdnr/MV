"""주말 실행기 진입점. 현재는 사전 점검/합성 Smoke만 검증됐으며 모델 학습은 차단한다."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mv_analysis.training.runner import main

if __name__=='__main__':
    raise SystemExit(main())

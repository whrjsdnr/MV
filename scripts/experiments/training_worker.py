"""독립 모델 환경용 진입점. shell 문자열 대신 인수 목록으로 실행한다."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mv_analysis.training.worker import main

if __name__=='__main__':
    raise SystemExit(main())

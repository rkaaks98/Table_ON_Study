#!/bin/bash

# 프로젝트 루트 디렉토리로 이동 (스크립트 위치 기준)
cd "$(dirname "$0")/.."

# 가상환경 활성화 (필요한 경우)
# source venv/bin/activate

# 메인 컨트롤러 실행
echo "Starting TableON-CO-OP System..."
python3 src/services/main_controller.py

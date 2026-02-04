#!/bin/bash

# =================================================================
# TableON 전체 설정 스크립트 (All-in-One)
# -----------------------------------------------------------------
# Node-RED, Python 환경, 시스템 서비스를 설정합니다.
#
# 사용법: sudo ./scripts/setup.sh
# =================================================================

# 스크립트 실행 중 오류가 발생하면 즉시 중단
set -e

# --- 사전 확인: sudo 권한으로 실행되었는지 확인 ---
if [ "$EUID" -ne 0 ]; then
  echo "오류: 이 스크립트는 반드시 sudo 권한으로 실행해야 합니다."
  echo "사용법: sudo ./scripts/setup.sh"
  exit 1
fi

# 스크립트 파일이 위치한 디렉터리를 기준으로 경로 설정
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "================================================================="
echo "TableON 전체 설정을 시작합니다..."
echo "================================================================="
echo ""

# --- 1단계: Node-RED 및 관련 패키지 설치 ---
echo "--- [단계 1/4] Node-RED 및 필수 구성요소 설치 ---"
echo "[1/5] 패키지 목록 업데이트 및 필수 도구(curl, build-essential) 설치 중..."
apt-get update
apt-get install -y curl build-essential

# Node.js 설치 여부 확인
if ! command -v node &> /dev/null; then
    echo "[2/5] Node.js 18.x 버전 저장소를 시스템에 추가하는 중..."
    curl -sL https://deb.nodesource.com/setup_18.x | bash -
    
    echo "[3/5] Node.js 설치 중..."
    apt-get install -y nodejs
else
    echo "[2,3/5] Node.js 이미 설치되어 있음. 건너뜀."
fi

# Node-RED 설치 여부 확인
if ! command -v node-red &> /dev/null; then
    echo "[4/5] Node-RED를 전역(global)으로 설치하는 중..."
    npm install -g --unsafe-perm node-red
else
    echo "[4/5] Node-RED 이미 설치되어 있음. 건너뜀."
fi

echo "[5/5] Node-RED 사용자 디렉터리(/root/.node-red) 설정 및 팔레트 설치..."
# Node-RED가 사용할 사용자 디렉터리 지정
NODERED_USER_DIR="/root/.node-red"
mkdir -p "$NODERED_USER_DIR"

# package.json을 사용자 디렉터리로 복사하여 팔레트 설치
if [ -f "$PROJECT_ROOT/nodered/package.json" ]; then
    cp "$PROJECT_ROOT/nodered/package.json" "$NODERED_USER_DIR/"
    # 해당 디렉터리로 이동하여 npm install 실행
    (cd "$NODERED_USER_DIR" && npm install)
else
    echo "주의: nodered/package.json을 찾을 수 없습니다."
fi
echo "✅ Node-RED 설치 및 설정 완료."
echo ""

# --- 2단계: Python 의존성 설치 ---
echo "--- [단계 2/4] Python 의존성 설치 ---"
echo "[1/2] python3-pip 설치 중..."
apt-get install -y python3-pip

echo "[2/2] requirements.txt를 사용하여 Python 패키지를 설치하는 중..."
pip3 install -r "$PROJECT_ROOT/requirements.txt"
echo "✅ Python 의존성 설치 완료."
echo ""

# --- 3단계: 시스템 설정 파일 배포 및 권한 설정 ---
echo "--- [단계 3/4] 시스템 설정 파일 배포 ---"
echo "[1/4] 로그 디렉토리 생성..."
mkdir -p "$PROJECT_ROOT/logs"
chmod 777 "$PROJECT_ROOT/logs"

echo "[2/4] 실행 스크립트 권한 부여..."
chmod +x "$PROJECT_ROOT/scripts/"*.sh

echo "[3/4] Node-RED 플로우 파일 복사 중..."
if [ -f "$PROJECT_ROOT/nodered/flows.json" ]; then
    cp "$PROJECT_ROOT/nodered/flows.json" "$NODERED_USER_DIR/"
else
    echo "주의: nodered/flows.json을 찾을 수 없습니다."
fi

echo "[4/4] 시스템 서비스 및 Udev 규칙 파일 복사 중..."
SERVICE_DEST_DIR="/etc/systemd/system"
UDEV_RULES_DIR="/etc/udev/rules.d"

if [ -d "$SERVICE_DEST_DIR" ]; then
    cp "$PROJECT_ROOT/system_config_files/python_scripts.service" "$SERVICE_DEST_DIR/"
    cp "$PROJECT_ROOT/system_config_files/nodered.service" "$SERVICE_DEST_DIR/"
fi

if [ -d "$UDEV_RULES_DIR" ]; then
    cp "$PROJECT_ROOT/system_config_files/99-usb-serial.rules" "$UDEV_RULES_DIR/"
fi
echo "✅ 시스템 설정 파일 배포 완료."
echo ""

# --- 4단계: 서비스 활성화 및 재시작 ---
echo "--- [단계 4/4] 서비스 활성화 및 재시작 ---"
echo "[1/3] udev 규칙을 다시 로드하는 중..."
udevadm control --reload-rules && udevadm trigger

echo "[2/3] systemd 데몬을 다시 로드하는 중..."
systemctl daemon-reload

echo "[3/3] python_scripts 및 nodered 서비스를 활성화하고 시작하는 중..."
systemctl enable python_scripts.service
systemctl enable nodered.service
# 기존 서비스 중지 후 시작 (재시작 효과)
systemctl restart python_scripts.service
systemctl restart nodered.service

echo "✅ 서비스 활성화 완료."
echo ""

# --- 최종 완료 ---
echo "================================================================="
echo "🎉 TableON의 모든 설정이 성공적으로 완료되었습니다!"
echo "시스템이 재부팅되어도 서비스가 자동으로 시작됩니다."
echo "================================================================="

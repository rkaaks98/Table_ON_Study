import os
import json
import time
import queue
import threading
from flask import Flask, jsonify
from flask_cors import CORS
from neuromeka import IndyDCP3

# Flask 앱 설정
app = Flask(__name__)
CORS(app)

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPE_PATH = os.path.join(BASE_DIR, "config", "recipe.json")

# 주문 큐 및 상태 변수 (직접 활용해보세요!)
order_queue = queue.Queue()
# current_processing_order = ...
# completed_orders_list = ...

# 로봇 레지스터 주소 (상수)
REG_CMD = 600
REG_INIT = 700
REG_STAT = 900

# 로봇 명령 코드 (상수)
GET_CUP, CUP_INIT = 110, 610
GET_WI, WI_INIT = 111, 611
WI_N, WI_N_INIT = 112, 612
GET_HOTWATER, HOTWATER_INIT = 113, 613
HOTWATER_N, HOTWATER_N_INIT = 114, 614
GET_COFFEE, COFFEE_INIT = 115, 615
COFFEE_N, COFFEE_N_INIT = 116, 616
SERVING_N, SERVING_N_INIT = 117, 617
GET_SERVING, SERVING_INIT = 118, 618
MOVE_HOME, HOME_INIT = 119, 619

# ==========================================
# [미션 1] RobotController 클래스 완성하기
# - connect, read/write_register, send_command 등 구현
# ==========================================
class RobotController:
    def __init__(self, ip):
        self.ip = ip
        self.client = None
        # self.is_running = ... (상태 플래그도 잊지 마세요!)

    def connect(self):
        pass

    # ... 필요한 메서드들을 직접 채워보세요!

# 전역 로봇 객체 생성
robot = RobotController("192.168.0.7")

# ==========================================
# [미션 2] 유틸리티 함수 구현
# ==========================================
def load_recipe():
    # recipe.json 파일 읽어오기
    pass

# ==========================================
# [미션 3] Flask 엔드포인트 구현
# - /set_robot_status
# - /order
# - /status
# ==========================================
@app.route('/')
def home():
    return "TableON Robot Server Study"

# ... 엔드포인트 작성

# ==========================================
# [미션 4] 워커 스레드 구현
# - robot_worker: 큐에서 주문 꺼내서 처리
# - monitor_worker: 로봇 상태 감시
# ==========================================
def robot_worker(robot_instance):
    pass

def monitor_worker(robot_instance):
    pass

def run_robot_sequence(robot, recipe):
    # 로봇 동작 시퀀스 구현
    pass

# ==========================================
# [미션 5] 메인 함수 및 서버 실행
# ==========================================
def main():
    pass

if __name__ == "__main__":
    main()

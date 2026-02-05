import os
import json
import time
import queue
import threading
from flask import Flask, jsonify
from flask_cors import CORS
from neuromeka import IndyDCP3
from urllib3 import response

# Flask 앱 설정
app = Flask(__name__)
CORS(app)

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPE_PATH = os.path.join(BASE_DIR, "config", "recipe.json")

# 주문 큐 및 상태 변수 (직접 활용해보세요!)
order_queue = queue.Queue()
current_processing_order = None
completed_orders_list = []

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
        self.is_running = False
    def connect(self):
        try:
            self.client = IndyDCP3(self.ip)
            print(f"Connected to {self.ip}")
            return True
        except Exception as e:
            print(f"Error connecting to {self.ip}: {e}")
            return False
        
    def write_register(self, address, value):
        if self.client is None:
            return False
        try:
            data = [{'addr': address, 'value': value}]
            self.client.set_int_variable(int_variables=data)
            return True
        except Exception as e:
            print(f"Error writing register {address}: {e}")
            return False
        
    def read_register(self, address):
        if self.client is None:
            return False
        try:
            response = self.client.get_int_variable()
            variables = response.get('variables', [])
            for v in variables:
                if v['addr'] == address:
                    return int(v['value'])
            return True
        except Exception as e:
            print(f"Error reading register {address}: {e}")
            return -1
        
    def send_command(self, cmd_code):
        try:    
            if self.write_register(REG_CMD, cmd_code) == True:
                print(f"Command {cmd_code} sent successfully")
                return True
            else:
                raise Exception("Failed to send command")
        except Exception as e:
            print(f"Error sending command: {e}")
            return False
        
    def wait_for_init(self, init_code, timeout=60):
        start_time = time.time()
        try:
            while time.time() - start_time < timeout:
                current_val = self.read_register(REG_INIT)
                if current_val == init_code:
                    print(f"Init code {init_code} received")
                    self.write_register(REG_INIT, 0)
                    return True
                time.sleep(0.5)
            raise Exception(f"Timeout waiting for init code {init_code}")
        except Exception as e:
            print(f"Error waiting for init: {e}")
            self.write_register(REG_INIT, 0)
            return False
        
    def get_robot_status(self):
        if self.client is None:
            return None
        try:
            status_data = self.client.get_control_data()
            op_state = status_data.get('op_state')
            is_home = status_data.get('is_home')
            if op_state == 0:
                return "OFFLINE"
            elif op_state in [2, 15]:
                return "ERROR_VIOLATION"
            elif op_state == 8:
                return "COLLIDED"
            elif op_state == 9:
                return "EMERGENCY_STOP"
            elif op_state in [3, 4, 16]:
                return "RECOVERING"
            elif op_state == 7:
                return "TEACHING_MODE"
            elif op_state == 6:
                return "MOVING"
            elif op_state == 5:
                return "IDLE"
            else:
                return "UNKNOWN"
        except Exception as e:
            print(f"Error getting robot status: {e}")
            return None
        
    def start_program(self):
        try:
            if self.get_robot_status() == "READY_AT_HOME":
                self.client.play_program(prog_idx=1)
            self.is_running = True
            print("Program started")
            return True
        except Exception as e:
            print(f"Error starting program: {e}")
            return False
        
    def stop_program(self):
        try:
            if self.get_robot_status() != "READY_AT_HOME":
                self.client.stop_program()
            self.is_running = False
            print("Program stopped")
            return True
        except Exception as e:
            print(f"Error stopping program: {e}")
            return False
            

# 전역 로봇 객체 생성
robot = RobotController("192.168.0.7")

# ==========================================
# [미션 2] 유틸리티 함수 구현
# ==========================================
def load_recipe():
    try:
        with open(RECIPE_PATH, 'r', encoding='utf-8') as f:
            recipes = json.load(f)
            return recipes
    except Exception as e:
        print(f"Error loading recipe: {e}")
        return []

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

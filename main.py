import os
import json
import time
import queue
import threading
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request
from flask_cors import CORS
from neuromeka import IndyDCP3

# ==========================================
# [Logger Setup]
# ==========================================
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logger = logging.getLogger("RobotServer")
logger.setLevel(logging.INFO)

# 1. 파일 핸들러 (system.log에 저장)
log_file_path = os.path.join(LOG_DIR, "system.log")
file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024, backupCount=3, encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 2. 콘솔 핸들러 (터미널 출력)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# ==========================================
# [App & Config]
# ==========================================
app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPE_PATH = os.path.join(BASE_DIR, "config", "recipe.json")
order_queue = queue.Queue()

current_processing_order = None
completed_orders_list = []

REG_CMD = 600
REG_INIT = 700
REG_STAT = 900

# robot command
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

CUP_IDX   = 101 # 1: hot, 2: ice, 3: hot컵 배출, 4: ice컵 배출
CUP_RES   = 105 # 컵 성공신호


# --- [주소 상수 정의 (IO Map)] ---
# Card 5 (Unit 5)
DO_ICE_BTN    = 3200
DO_HOT_CUP    = 3201
DO_ICE_CUP    = 3202
DO_SODA_VALVE = 3203

# Card 6 (Unit 6)
DO_SYRUP_BASE = 3300 # 3300 ~ 3307

# Card 3 (Unit 3)
DI_CUP_SENSOR = 6

class DeviceController:
    """
    범용 IO 제어 클래스 (Modbus RTU)
    - 특정 장비(컵, 얼음)에 종속되지 않고 write, read, pulse 기능만 제공
    """
    def __init__(self, port='/dev/ttyUSB485', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.client = None
        self.connected = False
        logger.info(f"IO Controller initialized on {port}")

    def connect(self):
        try:
            # 실제 연결 코드 (나중에 주석 해제)
            # from pymodbus.client.sync import ModbusSerialClient
            # self.client = ModbusSerialClient(method='rtu', port=self.port, baudrate=self.baudrate, timeout=1)
            # self.connected = self.client.connect()
            
            # [가상 연결 성공]
            self.connected = True
            logger.info("[Device] Connected (Virtual)")
            return True
        except Exception as e:
            logger.error(f"[Device] Connection Failed: {e}")
            self.connected = False
            return False

    def write_coil(self, unit, addr, val):
        """범용 출력 제어 (ON/OFF)"""
        if not self.connected:
            logger.warning("[Device] Not connected")
            return False
            
        try:
            # 실제 코드: self.client.write_coil(addr, val, unit=unit)
            state = "ON" if val else "OFF"
            logger.info(f"[IO] Unit {unit} : Write {addr} -> {state}")
            return True
        except Exception as e:
            logger.error(f"[IO] Write Error: {e}")
            return False

    def read_input(self, unit, addr):
        """범용 입력 읽기 (DI)"""
        if not self.connected: return 0
        try:
            # 실제 코드: res = self.client.read_discrete_inputs(addr, 1, unit=unit)
            # return res.bits[0]
            return 1 # 가상 값 (1: 센서 감지됨)
        except Exception as e:
            logger.error(f"[IO] Read Error: {e}")
            return -1
            
    def read_coil(self, unit, addr, count=1):
        """범용 출력 상태 읽기 (DO)"""
        if not self.connected: return 0
        try:
            # 실제 코드: res = self.client.read_coils(addr, count, unit=unit)
            # return res.bits[0] if count == 1 else res.bits
            return 1 # 가상 값
        except Exception as e:
            logger.error(f"[IO] Read Coil Error: {e}")
            return -1

    def pulse_coil(self, unit, addr, duration):
        """
        범용 펄스 제어 (ON -> 대기 -> OFF)
        """
        logger.info(f"[IO] Pulse Unit {unit} Addr {addr} ({duration}s)")
        if self.write_coil(unit, addr, True):
            time.sleep(duration)
            self.write_coil(unit, addr, False)
            return True
        return False

class RobotController:
  def __init__(self, ip):
     self.ip = ip
     self.client = None
     self.is_running = False
     
  def connect(self):
    try:
      self.client = IndyDCP3(self.ip)
      logger.info(f"[Robot] Connected: {self.ip}")
      return True
    except Exception as e:
      logger.error(f"[Robot] Connection Failed: {e}")
      self.client = None
      return False
    
  def read_register(self, address):
    try:
      if self.client is None: return -1
      response = self.client.get_int_variable()
      variables = response.get('variables', [])
      for v in variables:
        if v['addr'] == address:
          return int(v['value'])
      return -1
    except Exception as e:
      logger.error(f"[Robot] Read Error: {e}")
      return -1

  def write_register(self, address, value):
    try:
      if self.client is None: return False
      data = [{'addr': address, 'value': value}]
      self.client.set_int_variable(int_variables=data)
      return True
    except Exception as e:
      logger.error(f"[Robot] Write Error: {e}")
      return False
    
  def send_command(self, cmd_code):
    try:
      if self.write_register(REG_CMD, cmd_code):
        logger.info(f"[Robot] Command {cmd_code} sent")
        return True
      else:
        raise Exception("Failed to send command")
    except Exception as e:
      logger.error(f"[Robot] Send Command Error: {e}")
      return False
    
  def wait_for_init(self, init_code, timeout=60):
    start_time = time.time()
    try:
      while time.time() - start_time < timeout:
        current_val = self.read_register(REG_INIT)
        if current_val == init_code:
          logger.info(f"[Robot] Init code {init_code} received")
          self.write_register(REG_INIT, 0)
          return True
        time.sleep(0.5)
      raise Exception(f"Timeout waiting for init code {init_code}")
    except Exception as e:
      logger.error(f"[Robot] Wait Init Error: {e}")
      self.write_register(REG_INIT, 0)
      return False
      
  def wait_for_register(self, address, target_value, timeout=10, auto_reset=True):
    start_time = time.time()
    while time.time() - start_time < timeout:
        val = self.read_register(address)
        
        if val != 0:
          logger.info(f"[Robot] Register {address} received response: {val}")
          if auto_reset:
              self.write_register(address, 0)
              logger.info(f"[Robot] Register {address} reset to 0")
          return val
          
        time.sleep(0.5)
        
    logger.error(f"[Robot] Timeout waiting for Register {address} -> {target_value}")
    return 0
    
  def get_robot_status(self):
      if self.client is None: return None
      try:
        status_data = self.client.get_control_data()
        op_state = status_data.get('op_state')
        is_home = status_data.get('is_home')
        if op_state == 0:   return "OFFLINE"
        if op_state in [2, 15]: return "ERROR_VIOLATION"
        if op_state == 8:   return "COLLIDED"
        if op_state == 9:   return "EMERGENCY_STOP"
        if op_state in [3, 4, 16]: return "RECOVERING"
        if op_state == 7:   return "TEACHING_MODE"
        if op_state == 6:   return "MOVING"
        if op_state == 5:
          if is_home: return "READY_AT_HOME"
          else: return "READY_STATION"
        return f"STATE_{op_state}"
      except Exception as e:
        logger.error(f"[Robot] Get Status Error: {e}")
        return None
      
  def start_program(self):
    try:
      current_status = self.get_robot_status()
      if current_status != "READY_AT_HOME" and current_status != "READY_STATION":
        logger.warning(f"[Robot] Start Failed: Not at Home or Station ({current_status})")
        return False
      if self.client:
        self.client.play_program(prog_idx=1)
      self.is_running = True
      logger.info("[System] Program Started (Auto Mode ON)")
      return True
    except Exception as e:
      logger.error(f"[System] Start Error: {e}")
      return False

  def stop_program(self):
    try:
      if self.client:
        self.client.stop_program()
      self.is_running = False
      logger.info("[System] Program Stopped (Auto Mode OFF)")
      return True
    except Exception as e:
      logger.error(f"[System] Stop Error: {e}")
      return False
    
  def move_home(self):
    try:
      current_status = self.get_robot_status()
      UNSAFE_STATES = ["ERROR_VIOLATION", "COLLIDED", "EMERGENCY_STOP", "RECOVERING", "TEACHING_MODE"]
      if current_status in UNSAFE_STATES:
        logger.warning(f"[Robot] Move Home Failed: Unsafe State ({current_status})")
        return False
      if self.client:
        self.client.move_home()
        logger.info("[Robot] Moving to Home...")
        return True
    except Exception as e:
      logger.error(f"[Robot] Move Home Error: {e}")
      return False

# 전역 객체 생성
robot = RobotController("192.168.0.7")
device = DeviceController("COM3") 
    
'''
    utility function area
''' 
def load_recipe():
  try:
    with open(RECIPE_PATH, "r", encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f"[Config] Load Error: {e}")
    return []
  
def clear_queue(q):
  with q.mutex:
    q.queue.clear()
     
'''
    EndPoint Area
'''
@app.route('/set_robot_status/<int:status>', methods=['GET'])
def set_robot_status(status):
    if status == 1:
      if robot.start_program():
        return jsonify({"status": "success", "message": "Program started"})
      else:
        return jsonify({"status": "error", "message": "Failed to start program"}), 500
    elif status == 0:
      if robot.stop_program():
        return jsonify({"status": "success", "message": "Program stopped"})
      else:
        return jsonify({"status": "error", "message": "Failed to stop program"}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid status code"}), 400
      
@app.route('/get_robot_status', methods=['GET'])
def get_robot_status():
  status = robot.get_robot_status()
  return jsonify({"status": "success", "message": status})
      
@app.route('/move_home', methods=['GET'])
def move_home():
  if robot.move_home():
    return jsonify({"status": "success", "message": "Moving to home..."})
  else:
    return jsonify({"status": "error", "message": "Failed to move home"}), 500
    
@app.route('/order/<int:menu_code>', methods=['GET'])
def order_api(menu_code):
  if not robot.is_running:
    return jsonify({"status": "error", "message": "Robot is stopped"}), 503
  
  recipes = load_recipe()
  target = next((r for r in recipes if r['menu_code'] == menu_code), None)
  
  if target:
    order_queue.put(target)
    logger.info(f"[Order] Received: {target['menu_name']}")
    return jsonify({"status": "success", "message": f"Ordered {target['menu_name']}"})
  else:
    return jsonify({"status": "error", "message": "Menu not found"}), 404

# [추가] 범용 IO 제어 엔드포인트
@app.route('/io/write/<int:unit>/<int:addr>/<int:val>', methods=['GET'])
def api_io_write(unit, addr, val):
    if device.write_coil(unit, addr, bool(val)):
        return jsonify({"status": "success", "msg": f"Write Unit{unit} Addr{addr} -> {val}"})
    return jsonify({"status": "error", "msg": "IO Write Failed"}), 500

@app.route('/io/pulse/<int:unit>/<int:addr>/<float:duration>', methods=['GET'])
def api_io_pulse(unit, addr, duration):
    if device.pulse_coil(unit, addr, duration):
        return jsonify({"status": "success", "msg": f"Pulse Unit{unit} Addr{addr} ({duration}s)"})
    return jsonify({"status": "error", "msg": "IO Pulse Failed"}), 500

''' 
    Main Area 
'''
def monitor_worker(robot_instance):
  logger.info("[Monitor] Started")
  ERROR_STATES = ["ERROR_VIOLATION", "COLLIDED", "EMERGENCY_STOP", "TEACHING_MODE"]
  
  while True:
    try:
      status = robot_instance.get_robot_status()
      if robot_instance.is_running and (status in ERROR_STATES):
        logger.critical(f"[Monitor] Emergency Stop Triggered: {status}")
        robot_instance.stop_program()
        clear_queue(order_queue)
        logger.info("[Monitor] Queue cleared & Robot stopped")
      time.sleep(1)
    except Exception as e:
      logger.error(f"[Monitor] Error: {e}")
      time.sleep(1)

def robot_worker(robot_instance):
  logger.info("[Worker] Started")
  while True:
    try:
      if not robot_instance.is_running:
        time.sleep(1)
        continue
      try:
        recipe = order_queue.get(timeout=1)
      except queue.Empty:
        continue
      
      if recipe is None: break
      
      logger.info(f"[Worker] Processing: {recipe['menu_name']}")
      run_robot_sequence(robot_instance, recipe)
      order_queue.task_done()
      logger.info(f"[Worker] Completed: {recipe['menu_name']}")
      
    except Exception as e:
      logger.error(f"[Worker] Error: {e}")
      time.sleep(1)

def run_robot_sequence(robot, recipe):
    wi_time = max(recipe['water_ext_time'], recipe['ice_ext_time'])
    hotwater_time = recipe['hotwater_ext_time']
    coffee_time = recipe['coffee_ext_time']
    
    # [Step 1] 컵 배출 및 센서 확인 시퀀스
    robot.send_command(GET_CUP)
    
    cup_type = 2 if recipe['cup_num'] == 2 else 1
    robot.write_register(CUP_IDX, cup_type)
    logger.info(f"[Seq] Cup Type Set: {cup_type}")
    
    if (robot.wait_for_init(CUP_INIT) and robot.wait_for_register(CUP_RES, 1)):
      logger.info("컵 배출 성공")
    elif robot.wait_for_init(CUP_INIT) and robot.wait_for_register(CUP_RES, 2):
      logger.info("컵 배출 실패")
      robot.stop_program()
      clear_queue(order_queue)
      logger.info("[Seq] Queue cleared & Robot stopped")
      return False
      
    logger.info("[Seq] Cup Sequence Done")

    # [Step 2] 물/얼음 구간
    if wi_time > 0:
        robot.send_command(GET_WI)
        if robot.wait_for_init(WI_INIT):
            logger.info(f"[Seq] Water/Ice Dispensing... ({wi_time}s)")
            device.pulse_coil(5, DO_ICE_BTN, 0.5)
            time.sleep(wi_time)
            robot.send_command(WI_N)
            robot.wait_for_init(WI_N_INIT)
            
    # [Step 3] 뜨거운 물 구간
    if hotwater_time > 0:
        robot.send_command(GET_HOTWATER)
        if robot.wait_for_init(HOTWATER_INIT):
            logger.info(f"[Seq] Hot Water Dispensing... ({hotwater_time}s)")
            time.sleep(hotwater_time)
            robot.send_command(HOTWATER_N)
            robot.wait_for_init(HOTWATER_N_INIT)

    # [Step 4] 커피 구간
    if coffee_time > 0:
        robot.send_command(GET_COFFEE)
        if robot.wait_for_init(COFFEE_INIT):
            logger.info(f"[Seq] Coffee Dispensing... ({coffee_time}s)")
            time.sleep(coffee_time)
            robot.send_command(COFFEE_N)
            robot.wait_for_init(COFFEE_N_INIT)

    # [Step 5] 서빙 및 홈 복귀
    robot.send_command(GET_SERVING)
    robot.wait_for_init(SERVING_INIT)
    robot.send_command(SERVING_N)
    robot.wait_for_init(SERVING_N_INIT)
    
    robot.send_command(MOVE_HOME)
    robot.wait_for_init(HOME_INIT)
    return True
  
def main():
  if not robot.connect():
    logger.error("[System] Failed to connect to robot")
    return False
    
  if not device.connect():
      logger.warning("[System] Failed to connect to IO Device (Virtual Mode)")
  
  worker_thread = threading.Thread(target=robot_worker, args=(robot,), daemon=True)
  worker_thread.start()
  monitor_threading = threading.Thread(target=monitor_worker, args=(robot,), daemon=True)
  monitor_threading.start()
  
  logger.info("[System] Flask Server Starting...")
  app.run(host='0.0.0.0', port=5000, debug=True)
     
if __name__ == "__main__":
  main()

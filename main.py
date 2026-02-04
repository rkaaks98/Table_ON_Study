import os
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from neuromeka import IndyDCP3
import queue
import threading

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
GET_CUP, CUP_INIT = 110, 610  # CUP
GET_WI, WI_INIT = 111, 611  # WATER,ICE
WI_N, WI_N_INIT = 112, 612
GET_HOTWATER, HOTWATER_INIT = 113, 613  # HOTWATER
HOTWATER_N, HOTWATER_N_INIT = 114, 614
GET_COFFEE, COFFEE_INIT = 115, 615  # COFFEE
COFFEE_N, COFFEE_N_INIT = 116, 616
SERVING_N, SERVING_N_INIT = 117, 617
GET_SERVING, SERVING_INIT = 118, 618  # SERVING
MOVE_HOME, HOME_INIT = 119, 619  # MOVE_HOME

class RobotController:
  
  def __init__(self, ip):
     self.ip = ip
     self.client = None
     self.is_running = False
     
  def connect(self):
    try:
      self.client = IndyDCP3(self.ip)
      print(f"연결 성공: {self.ip}")
      return True
    except Exception as e:
      print(f"연결 실패: {e}")
      self.client = None
      return False
    
  def read_register(self, address):
    try:
      if self.client is None: return -1
      
      # 1. 인자 없이 전체 변수 가져오기
      response = self.client.get_int_variable()
      
      # 2. 결과 딕셔너리에서 'variables' 리스트를 꺼내서 해당 주소 찾기
      variables = response.get('variables', [])
      for v in variables:
        if v['addr'] == address:
          return int(v['value']) # 값은 문자열일 수 있으므로 int로 변환
          
      return -1
    except Exception as e:
      print(f"Error reading register: {e}")
      return -1

  def write_register(self, address, value):
    try:
      if self.client is None: return False
      
      # 이미지의 방식대로 리스트 생성 후 키워드 인자로 전달
      data = [{'addr': address, 'value': value}]
      self.client.set_int_variable(int_variables=data)
      
      return True
    except Exception as e:
      print(f"Error writing register: {e}")
      return False
    
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
        # --- [위험 및 시스템 이상 상태] ---
        if op_state == 0:   # SYSTEM_OFF
            return "OFFLINE"
        if op_state in [2, 15]: # VIOLATE, VIOLATE_HARD
            return "ERROR_VIOLATION"
        if op_state == 8:   # COLLISION
            return "COLLIDED"
        if op_state == 9:   # STOP_AND_OFF
            return "EMERGENCY_STOP"
        # --- [복구 및 설정 상태] ---
        if op_state in [3, 4, 16]: # RECOVER 계열
            return "RECOVERING"
        if op_state == 7:   # TEACHING
            return "TEACHING_MODE"
        # --- [정상 동작 상태] ---
        if op_state == 6:   # MOVING
            return "MOVING"
        if op_state == 5:   # IDLE
          if is_home:
            return "READY_AT_HOME"
          else:
            return "READY_STATION"
        # 그 외 정의되지 않은 상태
        return f"STATE_{op_state}"
      except Exception as e:
        print(f"❌ [Get Status Error] {e}")
        return None
      
  def start_program(self):
    try:
      if self.client:
        self.client.play_program(prog_idx=1)
      
      self.is_running = True
      print("Program started")
      return True
    except Exception as e:
      print(f"Error starting program: {e}")
      return False

  def stop_program(self):
    try:
      if self.client:
        self.client.stop_program()
        
      self.is_running = False
      print("Program stopped")
      return True
    except Exception as e:
      print(f"Error stopping program: {e}")
      return False
    

robot = RobotController("192.168.0.7")
    
'''
    utility function area
''' 
def load_recipe():
  try:
    with open(RECIPE_PATH, "r") as f:
      data = json.load(f)
      return data
  except FileNotFoundError:
    print(f"오류: 파일을 찾을 수 없습니다. ({RECIPE_PATH})")
    return []
  except json.JSONDecodeError:
    print(f"오류: JSON 형식이 올바르지 않습니다.")
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
      return jsonify({"status": "error", "message": "Invalid status"}), 400
    
@app.route('/order/<int:menu_code>', methods=['GET'])
def order_api(menu_code):
  if not robot.is_running:
    return jsonify({"status": "error", "message": "Robot is stopped"}), 503
  
  recipes = load_recipe()
  target = next((r for r in recipes if r['menu_code'] == menu_code), None)
  
  if target:
    order_queue.put(target)
    return jsonify({"status": "success", "message": f"Ordered {target['menu_name']}"})
  else:
    return jsonify({"status": "error", "message": "Menu not found"}), 404

''' 
    Main Area 
'''

def monitor_worker(robot_instance):
  print("Monitor worker started")
  
  ERROR_STATES = ["ERROR_VIOLATION", "COLLIDED", "EMERGENCY_STOP", "TEACHING_MODE"]
  
  while True:
    try:
      status = robot_instance.get_robot_status()
      if robot_instance.is_running and (status in ERROR_STATES):
        print(f"❌ [Robot Error] {status}")
        
        robot_instance.stop_program()
        
        with order_queue.mutex:
          order_queue.queue.clear()
          
        print("Queue cleared")
        print("Robot stopped")
        print("Robot status: {status}")
        print("Robot status: {status}")
      
      time.sleep(1)
    except Exception as e:
      print(f"Monitor worker error: {e}")
      time.sleep(1)

def robot_worker(robot_instance):
  print("Robot worker started")
  #global current_processing_order, completed_orders_list
  
  while True:
    try:
      if not robot_instance.is_running:
        time.sleep(1)
        continue
      try:
        recipe = order_queue.get(timeout=1)
      except queue.Empty:
        continue
      
      if recipe is None:
        break
      
      print(f"Running robot sequence for recipe: {recipe['menu_name']}")
      
      run_robot_sequence(robot, recipe)
      order_queue.task_done()
      print(f"Robot sequence for {recipe['menu_name']} completed")
    except Exception as e:
      print(f"Robot worker error: {e}")
      time.sleep(1)

def run_robot_sequence(robot, recipe):
    wi_time = max(recipe['water_ext_time'], recipe['ice_ext_time'])
    hotwater_time = recipe['hotwater_ext_time']
    coffee_time = recipe['coffee_ext_time']
      
    # 1. 컵 가져오기 (무조건 실행한다고 가정)
    robot.send_command(GET_CUP)
    if not robot.wait_for_init(CUP_INIT): return False

    # 2. 물/얼음 구간 (WI)
    # 물이나 얼음 시간 중 하나라도 0보다 크면 실행
    
    if wi_time > 0:
        robot.send_command(GET_WI)
        if robot.wait_for_init(WI_INIT):
            print(f"{wi_time}초 동안 추출 대기...")
            time.sleep(wi_time) # 레시피 시간만큼 대기
            robot.send_command(WI_N)
            robot.wait_for_init(WI_N_INIT)
    else:
      pass
    # 3. 뜨거운 물 구간 (HOTWATER)
    if hotwater_time > 0:
        robot.send_command(GET_HOTWATER)
        if robot.wait_for_init(HOTWATER_INIT):
            print(f"{recipe['hotwater_ext_time']}초 동안 뜨거운 물 추출 대기...")
            time.sleep(recipe['hotwater_ext_time'])
            robot.send_command(HOTWATER_N)
            robot.wait_for_init(HOTWATER_N_INIT)
    else:
      pass

    # 4. 커피 구간 (COFFEE)
    if coffee_time > 0:
        robot.send_command(GET_COFFEE)
        if robot.wait_for_init(COFFEE_INIT):
            print(f"{recipe['coffee_ext_time']}초 동안 커피 추출 대기...")
            time.sleep(recipe['coffee_ext_time'])
            robot.send_command(COFFEE_N)
            robot.wait_for_init(COFFEE_N_INIT)
    else:
      pass
    # 5. 서빙 및 홈 복귀
    robot.send_command(GET_SERVING)
    robot.wait_for_init(SERVING_INIT)
    robot.send_command(SERVING_N)
    robot.wait_for_init(SERVING_N_INIT)
    # ... 서빙 완료 대기 후 ...
    robot.send_command(MOVE_HOME)
    robot.wait_for_init(HOME_INIT)
    print("메뉴 완료")
    return True
  
  
def main():
  if not robot.connect():
    print("Failed to connect to robot")
    return False
  
  worker_thread = threading.Thread(target=robot_worker, args=(robot,), daemon=True)
  worker_thread.start()
  monitor_threading = threading.Thread(target=monitor_worker, args=(robot,), daemon=True)
  monitor_threading.start()
  
  print("Main thread started")
  
  app.run(host='0.0.0.0', port=5000)
    
     
      
if __name__ == "__main__":
  main()
  
import os
import json
import time
from neuromeka import IndyDCP3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RECIPE_PATH = os.path.join(BASE_DIR, "config", "recipe.json")

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
GET_SERVING, SERVING_INIT = 117, 617  # SERVING
SERVING_N, SERVING_N_INIT = 118, 618
MOVE_HOME, HOME_INIT = 119, 619  # MOVE_HOME

class RobotController:
  
  def __init__(self, ip):
     self.ip = ip
     self.client = None
     
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
      if self.client is None:
        print("Disconnected from robot")
        return False
      response = self.client.get_int_variable(address)
      
      if response and len(response) > 0:
        return response[0]['value']
      else:
        raise Exception("No response from robot")
    except Exception as e:
      print(f"Error reading register: {e}")
      return -1
    
  def write_register(self, address, value):
    try:
      if self.client is None:
        print("Disconnected from robot")
        return False

      self.client.set_int_variable(address, value)
      return True
    except Exception as e:
      print(f"Error writing register: {e}")
      return False
    
  def send_command(self, cmd_code):
    try:
      if self.client.write_register(REG_CMD, cmd_code) == True:
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
  def main():
     def run_robot_sequence(robot, recipe):
      # 1. 컵 가져오기 (무조건 실행한다고 가정)
      robot.send_command(GET_CUP)
      if not robot.wait_for_init(CUP_INIT): return False

      # 2. 물/얼음 구간 (WI)
      # 물이나 얼음 시간 중 하나라도 0보다 크면 실행
      wi_time = max(recipe['water_ext_time'], recipe['ice_ext_time'])
      if wi_time > 0:
          robot.send_command(GET_WI)
          if robot.wait_for_init(WI_INIT):
              print(f"{wi_time}초 동안 추출 대기...")
              time.sleep(wi_time) # 레시피 시간만큼 대기
              robot.send_command(WI_N)
              robot.wait_for_init(WI_N_INIT)

      # 3. 뜨거운 물 구간 (HOTWATER)
      if recipe['hotwater_ext_time'] > 0:
          robot.send_command(GET_HOTWATER)
          if robot.wait_for_init(HOTWATER_INIT):
              time.sleep(recipe['hotwater_ext_time'])
              robot.send_command(HOTWATER_N)
              robot.wait_for_init(HOTWATER_N_INIT)

      # 4. 커피 구간 (COFFEE)
      if recipe['coffee_ext_time'] > 0:
          robot.send_command(GET_COFFEE)
          if robot.wait_for_init(COFFEE_INIT):
              time.sleep(recipe['coffee_ext_time'])
              robot.send_command(COFFEE_N)
              robot.wait_for_init(COFFEE_N_INIT)

      # 5. 서빙 및 홈 복귀
      robot.send_command(GET_SERVING)
      robot.wait_for_init(SERVING_INIT)
      # ... 서빙 완료 대기 후 ...
      robot.send_command(MOVE_HOME)
      robot.wait_for_init(HOME_INIT)
      
      
if __name__ == "__main__":
  main()
  
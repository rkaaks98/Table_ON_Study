import os
import json
import time
import queue
import threading
from flask import Flask, jsonify
from flask_cors import CORS
from neuromeka import IndyDCP3

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

class RobotController:
    def __init__(self, ip):
        self.ip = ip
        self.client = None
        self.is_running = False

    def connect(self):
        try:
            self.client = IndyDCP3(self.ip)
            print(f"[Connect] Success: {self.ip}")
            return True
        except Exception as e:
            print(f"[Connect] Failed: {e}")
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
            return -1

    def write_register(self, address, value):
        try:
            if self.client is None: return False
            data = [{'addr': address, 'value': value}]
            self.client.set_int_variable(int_variables=data)
            return True
        except Exception as e:
            print(f"Error writing register: {e}")
            return False
        
    def send_command(self, cmd_code):
        try:
            if self.write_register(REG_CMD, cmd_code):
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
        if self.client is None: return None
        try:
            status_data = self.client.get_control_data()
            op_state = status_data.get('op_state')
            is_home = status_data.get('is_home')
            if op_state == 0: return "OFFLINE"
            if op_state in [2, 15]: return "ERROR_VIOLATION"
            if op_state == 8: return "COLLIDED"
            if op_state == 9: return "EMERGENCY_STOP"
            if op_state in [3, 4, 16]: return "RECOVERING"
            if op_state == 7: return "TEACHING_MODE"
            if op_state == 6: return "MOVING"
            if op_state == 5:
                return "READY_AT_HOME" if is_home else "READY_STATION"
            return f"STATE_{op_state}"
        except Exception as e:
            return None

    def start_program(self):
        try:
            if self.client:
                self.client.play_program(prog_idx=1)
            self.is_running = True
            print("[System] Program started (Auto Mode ON)")
            return True
        except Exception as e:
            print(f"Error starting program: {e}")
            return False

    def stop_program(self):
        try:
            if self.client:
                self.client.stop_program()
            self.is_running = False
            print("[System] Program stopped (Auto Mode OFF)")
            return True
        except Exception as e:
            print(f"Error stopping program: {e}")
            return False

robot = RobotController("192.168.0.7")

def load_recipe():
    try:
        with open(RECIPE_PATH, "r", encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Recipe Load Error: {e}")
        return []

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

@app.route('/order/<int:menu_code>')
def order_api(menu_code):
    # [힌트 2] 오타 찾기
    if not robot.is_running:
        return jsonify({"status": "error", "message": "Robot is stopped"}), 503

    recipes = load_recipe()
    target = next((r for r in recipes if r['menu_code'] == menu_code), None)
    
    if target:
        order_queue.put(target)
        return jsonify({"status": "success", "message": f"Ordered {target['menu_name']}"})
    return jsonify({"status": "error", "message": "Menu not found"}), 404

@app.route('/status')
def get_system_status():
    return jsonify({
        "robot_running": robot.is_running,
        "waiting_orders": order_queue.qsize(),
        # [힌트 1 관련] 변수 누락으로 에러 발생 가능
        "current_order": current_processing_order,
        "completed_history": completed_orders_list
    })

''' 
    Main Area 
'''
def monitor_worker(robot_instance):
    print("[Monitor] Started")
    ERROR_STATES = ["ERROR_VIOLATION", "COLLIDED", "EMERGENCY_STOP", "OFFLINE", "UNKNOWN_ERROR"]
    
    while True:
        try:
            status = robot_instance.get_robot_status()
            
            if robot_instance.is_running and (status in ERROR_STATES):
                print(f"\n[Monitor] Robot Error Detected: {status}")
                print("[Monitor] Emergency Stop Triggered")
                
                robot_instance.stop_program()
                
                with order_queue.mutex:
                    order_queue.queue.clear()
                print("[Monitor] Order queue cleared")
            
            time.sleep(1)
        except Exception as e:
            print(f"[Monitor] Error: {e}")
            time.sleep(1)

def robot_worker(robot_instance):
    # [힌트 1 관련] 전역 변수 global 선언 누락
    global current_processing_order, completed_orders_list
    
    print("[Worker] Started")
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
            
            print(f"[Worker] Processing order: {recipe['menu_name']}")
            
            current_processing_order = recipe
            
            run_robot_sequence(robot_instance, recipe)
            order_queue.task_done()
            
            completed_orders_list.append(recipe)
            current_processing_order = None
            
            print(f"[Worker] Completed: {recipe['menu_name']}")
            
        except Exception as e:
            print(f"[Worker] Error: {e}")
            time.sleep(1)

def run_robot_sequence(robot, recipe):
    wi_time = max(recipe['water_ext_time'], recipe['ice_ext_time'])
    hotwater_time = recipe['hotwater_ext_time']
    coffee_time = recipe['coffee_ext_time']
      
    robot.send_command(GET_CUP)
    if not robot.wait_for_init(CUP_INIT): return False

    if wi_time > 0:
        robot.send_command(GET_WI)
        if robot.wait_for_init(WI_INIT):
            time.sleep(wi_time)
            robot.send_command(WI_N)
            robot.wait_for_init(WI_N_INIT)

    if hotwater_time > 0:
        robot.send_command(GET_HOTWATER)
        if robot.wait_for_init(HOTWATER_INIT):
            time.sleep(hotwater_time)
            robot.send_command(HOTWATER_N)
            robot.wait_for_init(HOTWATER_N_INIT)

    if coffee_time > 0:
        robot.send_command(GET_COFFEE)
        if robot.wait_for_init(COFFEE_INIT):
            time.sleep(coffee_time)
            robot.send_command(COFFEE_N)
            robot.wait_for_init(COFFEE_N_INIT)

    robot.send_command(GET_SERVING)
    robot.wait_for_init(SERVING_INIT)
    robot.send_command(SERVING_N)
    robot.wait_for_init(SERVING_N_INIT)
    
    robot.send_command(MOVE_HOME)
    robot.wait_for_init(HOME_INIT)
    return True

def main():
    if not robot.connect():
        print("[System] Failed to connect to robot")
        return

    worker = threading.Thread(target=robot_worker, args=(robot,), daemon=True)
    worker.start()
    
    monitor = threading.Thread(target=monitor_worker, args=(robot,), daemon=True)
    monitor.start()
    
    print("[System] Flask Server Starting...")
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    main()

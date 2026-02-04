from flask import Flask, request, jsonify
import json
import time
import sys
import os
import atexit
import threading
import random
import requests

sys.path.append("/usr/local/lib/python3.10/dist-packages/neuromeka/proto")
sys.path.append("/usr/local/lib/python3.10/dist-packages/neuromeka/proto_step")

# Neuromeka Import
try:
    from neuromeka import IndyDCP3
    from neuromeka.enums import OpState, ProgramState, DigitalState
except ImportError as e:
    # In simulation mode, we might not have neuromeka installed, but for now we assume it's there or we mock enums if needed
    print(f"[WARN] Failed to import neuromeka library: {e}")
    # Define dummy enums for simulation if import fails
    class OpState:
        MOVING = 2
        COLLISION = 4
        VIOLATE = 5
        VIOLATE_HARD = 6
        IDLE = 1
    class ProgramState:
        RUNNING = 2
        STOPPED = 1
    class DigitalState:
        ON = 1
        OFF = 0

app = Flask(__name__)

# --- Global Config & Controllers ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json')
IO_SERVICE_URL = "http://localhost:8400"
PICKUP_SERVICE_URL = "http://localhost:8600"
NODERED_URL = "http://localhost:1880/notify" # Node-RED Notify URL
controllers = {} # key: robot_id (e.g., 'robot_1'), value: RobotController instance
SIMULATION_MODE = False

def notify_clients(event_name, data=None):
    """Helper to send HTTP Trigger to Node-RED"""
    payload = {'event': event_name}
    if data:
        payload.update(data)
    
    def _send():
        try:
            requests.post(NODERED_URL, json=payload, timeout=0.5)
            # print(f"[Notify] Sent {event_name} to Node-RED") # Log disabled for noise reduction
        except:
            pass
            
    threading.Thread(target=_send, daemon=True).start()

class MockIndyDCP3:
    def __init__(self, robot_ip):
        self.robot_ip = robot_ip
        self.registers = {
            600: 0,   # REG_CMD
            700: 0,   # REG_INIT
            100: 0,   # REG_CUP_IDX
            102: 0,   # REG_CUP_RES
            103: 0,   # REG_CUP_SET
            105: 0,   # REG_CUP_ON
        } # addr -> value
        self.di = [0] * 32
        self.do = [0] * 32
        self.op_state = getattr(OpState, 'IDLE', 1)
        self.prog_state = getattr(ProgramState, 'STOPPED', getattr(ProgramState, 'IDLE', 1))
        self.last_cmd_time = 0
        self.current_cmd = 0
        
        # Background thread to simulate command execution
        self.running = True
        threading.Thread(target=self._sim_loop, daemon=True).start()
        print(f"[MOCK] Initialized MockIndyDCP3 for {robot_ip}")

    def _sim_loop(self):
        while self.running:
            # Simple simulation: Check REG_CMD (Addr 600)
            cmd = self.get_int_variable_mock(600)
            
            if cmd > 0 and self.current_cmd != cmd:
                self.current_cmd = cmd
                self.last_cmd_time = time.time()
                self.op_state = OpState.MOVING
                
                # 시뮬레이션: Ack(REG_INIT) 초기화 (0=Busy/Start)
                self.set_int_variable_mock(700, 0)
                
                print(f"[MOCK] Processing CMD {cmd}...")
                notify_clients('robot_updated') # Notify Start
            
            if self.op_state == OpState.MOVING:
                # Simulate movement time (e.g., 2 seconds)
                if time.time() - self.last_cmd_time > 2.0:
                    self.op_state = OpState.IDLE
                    
                    # [Simulation] Virtual Sensor Update Logic (단일 로봇 - 고객 픽업대만)
                    try:
                        # 1. Window Pickup (CMD 140) -> Sensor 1 (Arduino 1)
                        if self.current_cmd == 140:
                            idx = self.get_int_variable_mock(103) # REG_F_PICK_IDX
                            if 1 <= idx <= 3:
                                try:
                                    requests.get(f"{IO_SERVICE_URL}/sim/setPickup/1/{idx}/1", timeout=0.1)
                                    print(f"[MOCK] Window Pickup Slot {idx} Occupied")
                                except: pass

                        # 2. Hall Pickup (CMD 142) -> Sensor 1 (Arduino 2)
                        elif self.current_cmd == 142:
                            idx = self.get_int_variable_mock(104) # REG_R_PICK_IDX
                            if 1 <= idx <= 3:
                                try:
                                    requests.get(f"{IO_SERVICE_URL}/sim/setPickup/2/{idx}/1", timeout=0.1)
                                    print(f"[MOCK] Hall Pickup Slot {idx} Occupied")
                                except: pass

                    except Exception as e:
                        print(f"[MOCK] Sensor Update Failed: {e}")

                    # If command is CUP_MOVE (CMD 110), simulate cup dispense
                    if self.current_cmd == 110:
                        # 1. 로봇 도착 신호
                        self.set_int_variable_mock(105, 1)  # CUP_ON = 1
                        print(f"[MOCK] CUP_ON (105) = 1 (로봇 도착)")
                        
                        # 2. 0.5초 후 컵 추출 성공 신호
                        def set_cup_res():
                            time.sleep(0.5)
                            self.set_int_variable_mock(102, 1)  # CUP_RES = 1
                            print(f"[MOCK] CUP_RES (102) = 1 (추출 성공)")
                        threading.Thread(target=set_cup_res, daemon=True).start()
                    
                    # If command is COFFEE_PLACE (CMD 115), simulate cup set
                    if self.current_cmd == 115:
                        # 커피머신에 컵 거치 완료 신호
                        def set_cup_set():
                            time.sleep(0.3)
                            self.set_int_variable_mock(103, 1)  # CUP_SET = 1
                            print(f"[MOCK] CUP_SET (103) = 1 (컵 거치 완료)")
                        threading.Thread(target=set_cup_set, daemon=True).start()
                    
                    # Ack: Write CMD + 500 to REG_INIT (Addr 700)
                    ack_val = self.current_cmd + 500
                    self.set_int_variable_mock(700, ack_val)
                    print(f"[MOCK] CMD {self.current_cmd} Done. Ack {ack_val} set.")
                    
                    # [중요] 시뮬레이션: 명령 완료 후 REG_CMD(600) 및 인자 레지스터 자동 초기화
                    self.set_int_variable_mock(600, 0)
                    self.current_cmd = 0 # [BugFix] 연속된 동일 명령 처리를 위해 내부 상태 초기화
                    # 102(CUP_RES), 103(CUP_SET), 105(CUP_ON)는 order_service가 초기화하므로 제외
                    for addr in [100, 101, 104, 106, 107]:
                        self.set_int_variable_mock(addr, 0)
                    
                    notify_clients('robot_updated') # Notify End

            time.sleep(0.1)

    def get_control_data(self):
        return {'op_state': self.op_state}

    def get_program_data(self):
        return {'program_state': self.prog_state, 'program_name': 'MockProgram'}

    def start_program(self, prog_num):
        self.prog_state = ProgramState.RUNNING
        print(f"[MOCK] Start Program {prog_num}")
    
    def stop_program(self):
        self.prog_state = getattr(ProgramState, 'STOPPED', getattr(ProgramState, 'IDLE', 1))
        print(f"[MOCK] Stop Program")

    def move_home(self):
        print(f"[MOCK] Move Home")
        self.op_state = OpState.MOVING
        time.sleep(1)
        self.op_state = OpState.IDLE

    def stop_motion(self):
        self.op_state = OpState.IDLE
        print(f"[MOCK] Stop Motion")

    def reset_robot(self):
        self.op_state = OpState.IDLE
        print(f"[MOCK] Reset Robot")

    def set_direct_teaching(self, enable):
        print(f"[MOCK] Direct Teaching: {enable}")

    def set_do(self, do_list):
        for item in do_list:
            addr = item['address']
            state = item['state']
            if 0 <= addr < 32:
                self.do[addr] = 1 if state == DigitalState.ON else 0

    def get_di(self):
        return self.di

    def set_int_variable(self, int_variables):
        for item in int_variables:
            self.registers[item['addr']] = item['value']
            
    def get_int_variable(self):
        # Return all as list of dicts
        return {'variables': [{'addr': k, 'value': v} for k, v in self.registers.items()]}

    # Helper for mock internal use
    def get_int_variable_mock(self, addr):
        return self.registers.get(addr, 0)
    
    def set_int_variable_mock(self, addr, value):
        self.registers[addr] = value


class RobotController:
    def __init__(self, robot_id, config):
        self.robot_id = robot_id
        self.ip = config.get('ip')
        self.name = config.get('name', robot_id)
        self.role = config.get('role', 'unknown')
        self.client = None
        self.lock = threading.Lock()
        self.last_status = {} # Cache for notify optimization
        
        if not self.ip:
            print(f"[ERROR][{self.robot_id}] IP not configured.")
        else:
            self.connect()
            
        # Start Status Monitor Thread
        self.running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        """Monitor robot status and notify on change"""
        while self.running:
            time.sleep(1)
            if not self.client: continue
            
            try:
                current_status = self.get_status(internal=True) # internal flag to avoid loop
                if not current_status: continue
                
                # Check if key fields changed (is_moving, is_error, program_state, etc.)
                # Simple comparison for now
                is_changed = False
                if not self.last_status:
                    is_changed = True
                else:
                    for key in ['is_moving', 'is_program_running', 'is_error', 'is_collided', 'program_name']:
                        if self.last_status.get(key) != current_status.get(key):
                            is_changed = True
                            break
                
                if is_changed:
                    self.last_status = current_status
                    # print(f"[{self.robot_id}] Status Changed -> Notify")
                    notify_clients('robot_updated', {'robot_id': self.robot_id})
                    
            except Exception as e:
                # print(f"[{self.robot_id}] Monitor Error: {e}")
                pass

    def connect(self):
        print(f"[SYSTEM] Initializing {self.robot_id} ({self.name}) at {self.ip}...")
        if SIMULATION_MODE:
             print(f"[SYSTEM] SIMULATION MODE: Connecting to MockIndyDCP3 for {self.robot_id}")
             self.client = MockIndyDCP3(self.ip)
        else:
            try:
                self.client = IndyDCP3(robot_ip=self.ip)
                print(f"[SYSTEM] {self.robot_id} connected.")
            except Exception as e:
                print(f"[ERROR] Failed to connect to {self.robot_id}: {e}")
                self.client = None

    def get_status(self, internal=False):
        if not self.client: return None
        try:
            # Avoid lock contention if called from monitor loop which might be less critical?
            # But we need thread safety.
            with self.lock:
                # Use get_control_data and get_program_data for IndyDCP3
                control_data = self.client.get_control_data()
                prog_data = self.client.get_program_data()
            
            op_state = control_data.get('op_state')
            prog_state = prog_data.get('program_state')
            
            # Status Mapping using enums
            is_moving = 1 if op_state == OpState.MOVING else 0
            is_prog_running = 1 if prog_state == ProgramState.RUNNING else 0
            is_collided = 1 if op_state == OpState.COLLISION else 0
            is_error = 1 if op_state in [OpState.VIOLATE, OpState.VIOLATE_HARD] else 0
            
            return {
                'is_moving': is_moving,
                'is_program_running': is_prog_running,
                'is_collided': is_collided,
                'is_error': is_error,
                'op_state_code': op_state,
                'program_state_code': prog_state,
                'program_name': prog_data.get('program_name', ''),
                # Compatibility fields
                'is_running': 1 if (is_moving or is_prog_running) else 0,
                'is_emergency': 0, # Not explicitly available in OpState
                'is_home': 0
            }
        except Exception as e:
            print(f"[ERROR][{self.robot_id}] get_status failed: {e}")
            return None

    def play_program(self, prog_num):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            # Mock 객체 또는 구버전 호환
            if hasattr(self.client, 'start_program'):
                self.client.start_program(prog_num)
            # IndyDCP3 정식 메소드
            elif hasattr(self.client, 'play_program'):
                # 문서에 따라 인덱스 실행 시 prog_idx 명시 필요
                # play_program(prog_name, prog_idx) 형태이므로 위치 인자로 주면 prog_name으로 인식됨
                self.client.play_program(prog_idx=int(prog_num))
            else:
                 raise Exception("start_program/play_program method not found")

    def stop_program(self):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            if hasattr(self.client, 'stop_program'):
                self.client.stop_program()
            else:
                 raise Exception("stop_program method not found")
            
    def recover(self):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            # Assuming reset_robot or recover
            if hasattr(self.client, 'reset_robot'):
                self.client.reset_robot()
            elif hasattr(self.client, 'recover'):
                self.client.recover()
            else:
                raise Exception("reset_robot/recover method not found")
            
    def move_home(self):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            self.client.move_home()
    
    def stop_motion(self):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            self.client.stop_motion()
            
    def set_direct_teaching(self, enable):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            if enable:
                if hasattr(self.client, 'start_direct_teaching'):
                    self.client.start_direct_teaching()
                elif hasattr(self.client, 'set_direct_teaching'):
                    self.client.set_direct_teaching(True)
                else:
                    raise Exception("Direct teaching start method not found")
            else:
                if hasattr(self.client, 'stop_direct_teaching'):
                    self.client.stop_direct_teaching()
                elif hasattr(self.client, 'set_direct_teaching'):
                    self.client.set_direct_teaching(False)
                else:
                    raise Exception("Direct teaching stop method not found")

    def set_do(self, index, state_bool):
        if not self.client: raise Exception("Client not initialized")
        state_enum = DigitalState.ON if state_bool else DigitalState.OFF
        with self.lock:
            # set_do takes a list of dicts or tuples
            self.client.set_do([{'address': index, 'state': state_enum}])

    def set_int_variable(self, addr, value):
        if SIMULATION_MODE and isinstance(self.client, MockIndyDCP3):
            self.client.set_int_variable_mock(addr, value)
            return

        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            self.client.set_int_variable(int_variables=[{'addr': addr, 'value': value}])
            
    def get_int_variable(self, addr):
        if SIMULATION_MODE and isinstance(self.client, MockIndyDCP3):
            return self.client.get_int_variable_mock(addr)

        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            resp = self.client.get_int_variable() # May return all vars
        
        # Check return type
        # If response is dict with 'variables' list
        if isinstance(resp, dict):
            variables = resp.get('variables', [])
        else:
             # Fallback if response structure is different
             variables = []

        item = next((v for v in variables if int(v.get('addr', -1)) == addr), None)
        return item.get('value') if item else None
    
    def get_di(self):
        if not self.client: raise Exception("Client not initialized")
        with self.lock:
            return self.client.get_di()

def initialize_clients():
    global controllers, SIMULATION_MODE
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        SIMULATION_MODE = config.get('simulation_mode', False)
        print(f"[SYSTEM] Simulation Mode: {SIMULATION_MODE}")

        robot_config = config.get('robot', {})
        for key, val in robot_config.items():
            if key.startswith('robot_') and isinstance(val, dict):
                controllers[key] = RobotController(key, val)

        if not controllers:
            print("[WARN] No robots found in config.")

        atexit.register(cleanup_clients)
    except Exception as e:
        print(f"[FATAL] Config load failed: {e}")
        sys.exit(1)

def cleanup_clients():
    print("[SYSTEM] Cleaning up clients...")
    pass

# --- API Endpoints ---

@app.route('/status/<string:robot_id>', methods=['GET'])
def get_status(robot_id):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    
    status = ctrl.get_status()
    if status is None:
        return jsonify({
            'error': 'communication_failed',
            'is_running': 0, 'is_program_running': 0,
            'is_error': 1, 'is_collided': 1
        }), 500
    return jsonify(status)

@app.route('/runProgram/<string:robot_id>/<int:prog_num>', methods=['GET'])
def run_program(robot_id, prog_num):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        ctrl.play_program(prog_num)
        return jsonify({'message': f'Program {prog_num} started on {robot_id}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/command/<string:robot_id>/<int:cmd>', methods=['GET'])
def robot_command(robot_id, cmd):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        if cmd == 1: ctrl.stop_program()
        elif cmd == 2: ctrl.recover()
        elif cmd == 3: ctrl.set_direct_teaching(True)
        elif cmd == 4: ctrl.set_direct_teaching(False)
        elif cmd == 5: ctrl.move_home()
        elif cmd == 6: ctrl.stop_motion()
        else: return jsonify({'error': f'Invalid command code: {cmd}'}), 400
        
        notify_clients('robot_updated') # Notify Command Executed
        return jsonify({'message': f'Command {cmd} executed on {robot_id}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Browser Test Endpoints
@app.route('/writeRegisterGet/<string:robot_id>/<int:addr>/<int:value>', methods=['GET'])
def write_register_get(robot_id, addr, value):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        ctrl.set_int_variable(addr, value)
        return jsonify({'message': f'Wrote {value} to register {addr} on {robot_id}'}) 
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/readRegisterGet/<string:robot_id>/<int:addr>', methods=['GET'])
def read_register_get(robot_id, addr):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        val = ctrl.get_int_variable(addr)
        if val is None: return jsonify({'error': f'addr {addr} not found'}), 404
        return jsonify({'value': val})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/setDOGet/<string:robot_id>/<int:index>/<int:state>', methods=['GET'])
def set_do_get(robot_id, index, state):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        ctrl.set_do(index, bool(state))
        return jsonify({'message': f'Set DO {index} to {state} on {robot_id}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# POST Endpoints
@app.route('/writeRegister', methods=['POST'])
def write_register():
    data = request.get_json()
    if not data or 'robot_id' not in data or 'addr' not in data or 'value' not in data:
        return jsonify({'error': 'Missing robot_id, addr, or value'}), 400
    
    ctrl = controllers.get(data['robot_id'])
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        ctrl.set_int_variable(int(data['addr']), int(data['value']))
        return jsonify({'message': 'Success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/readRegister', methods=['POST'])
def read_register():
    data = request.get_json()
    if not data or 'robot_id' not in data or 'addr' not in data:
        return jsonify({'error': 'Missing robot_id or addr'}), 400
    
    ctrl = controllers.get(data['robot_id'])
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        val = ctrl.get_int_variable(int(data['addr']))
        if val is None: return jsonify({'error': 'Address not found'}), 404
        return jsonify({'value': val})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/setDO', methods=['POST'])
def set_do():
    data = request.get_json()
    if not data or 'robot_id' not in data or 'index' not in data or 'state' not in data:
        return jsonify({'error': 'Missing robot_id, index, or state'}), 400
    
    ctrl = controllers.get(data['robot_id'])
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        ctrl.set_do(int(data['index']), bool(int(data['state'])))
        return jsonify({'message': 'Success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/getDI/<string:robot_id>', methods=['GET'])
def get_di(robot_id):
    ctrl = controllers.get(robot_id)
    if not ctrl: return jsonify({'error': 'Robot not found'}), 404
    try:
        resp = ctrl.get_di()
        return jsonify(resp)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/shutdown', methods=['POST'])
def shutdown_server():
    print("[SYSTEM] Shutdown endpoint called. Cleaning up clients.")
    cleanup_clients()
    return jsonify({"message": "Clients cleaned up successfully."})

@app.route('/robots', methods=['GET'])
def list_robots():
    return jsonify(list(controllers.keys()))

if __name__ == '__main__':
    initialize_clients()
    app.run(host='0.0.0.0', port=8300, debug=False)

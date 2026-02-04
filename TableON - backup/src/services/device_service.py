from flask import Flask, jsonify, request
import time, requests, json, importlib, sys, os
import threading

# 프로젝트의 루트 경로(src의 부모)를 python 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

app = Flask(__name__)

# --- 전역 설정 ---
IO_URL = "http://localhost:8400"
coffee_machine_handler = None
ice_machine_handler = None
coffee_status = 0
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json')
SIMULATION_MODE = False

# ---- 고정 IO 맵 (상수 정의) ----
# 카드번호/값 → 실제 주소: 값 N → 3200+N
# 예: 5/1 → Unit 5, Addr 3201

# 제빙기 버튼 (DO) - 5/1
UNIT_ICEMACHINE_BTN = 5
ADDR_ICEMACHINE_BTN = 3200

# 온수기 (DO) - 5/2
UNIT_HOTWATER   = 5
ADDR_HOTWATER   = 3201

# 탄산수/솔벨브 (DO) - 5/5
UNIT_SPARKLING  = 5
ADDR_SPARKLING  = 3204

# 시럽 디스펜서 (DO) - 6/1~8
# 시럽 1~4: Unit 6, Addr 3200~3203
# 시럽 5~8: Unit 6, Addr 3204~3207
UNIT_SYRUP      = 6
ADDR_SYRUP_1_BASE = 3200
ADDR_SYRUP_2_BASE = 3204

# --- Mock Handlers ---
class MockCoffeeMachine:
    def __init__(self, port, baudrate):
        print(f"[MOCK] CoffeeMachine initialized on {port}")

    def make_coffee(self, product_id, duration):
        print(f"[MOCK] Making Coffee: ID={product_id}, Duration={duration}s")
        time.sleep(2) # Simulate brew time (shortened)
        return True, "Mock Success"

    def execute_rinse(self):
        print(f"[MOCK] Coffee Rinse")
        time.sleep(2)
        return True, "Mock Rinse Success"

class MockIceMachine:
    def __init__(self, port, baudrate, io_url):
        print(f"[MOCK] IceMachine initialized on {port}")
    
    def make_ice_water(self, ice_time, water_time):
        print(f"[MOCK] Dispensing Ice({ice_time}s) & Water({water_time}s)")
        time.sleep(max(ice_time, water_time)) 
        return True, "Mock Dispense Success"

# --- 장비 동적 로더 ---
def load_device_handlers():
    """config.json을 읽어 설정에 맞는 장비 핸들러(커피, 제빙기)를 로드합니다."""
    global coffee_machine_handler, ice_machine_handler, SIMULATION_MODE
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)

        SIMULATION_MODE = config.get('simulation_mode', False)
        print(f"[SYSTEM] Device Service Simulation Mode: {SIMULATION_MODE}")

        # 1. 커피 머신 로드
        coffee_config = config.get('coffee_machine', {})
        if coffee_config:
            brand = coffee_config.get('brand')
            port = coffee_config.get('port')
            baudrate = coffee_config.get('baudrate')
            is_sim = coffee_config.get('simulation', False) or SIMULATION_MODE
            
            if is_sim:
                 coffee_machine_handler = MockCoffeeMachine(port, baudrate)
                 print(f"[SYSTEM] Loaded MOCK coffee machine handler")
            elif not all([brand, port, baudrate]):
                 print("[SYSTEM][WARN] Coffee machine config is incomplete. Skipping.")
            else:
                try:
                    module_name = f"devices.coffee_machine.{brand}"
                    class_name = f"{brand.capitalize()}CoffeeMachine"
                    CoffeeMachineModule = importlib.import_module(module_name)
                    CoffeeMachineClass = getattr(CoffeeMachineModule, class_name)
                    coffee_machine_handler = CoffeeMachineClass(port, baudrate)
                    print(f"[SYSTEM] Loaded coffee machine handler for '{brand}'")
                except Exception as e:
                    print(f"[SYSTEM][ERROR] Real Coffee Driver Load Failed: {e}. Fallback to Mock.")
                    coffee_machine_handler = MockCoffeeMachine(port, baudrate)

        # 2. 제빙기 로드
        ice_config = config.get('ice_machine', {})
        if ice_config:
            brand = ice_config.get('brand')
            port = ice_config.get('port')
            baudrate = ice_config.get('baudrate')
            is_sim = ice_config.get('simulation', False) or SIMULATION_MODE

            if is_sim:
                ice_machine_handler = MockIceMachine(port, baudrate, IO_URL)
                print(f"[SYSTEM] Loaded MOCK ice machine handler")
            elif not all([brand, port, baudrate]):
                print("[SYSTEM][WARN] Ice machine config is incomplete. Skipping.")
            else:
                try:
                    module_name = f"devices.ice_machine.{brand}"
                    class_name = f"{brand.capitalize()}IceMachine"
                    IceMachineModule = importlib.import_module(module_name)
                    IceMachineClass = getattr(IceMachineModule, class_name)
                    ice_machine_handler = IceMachineClass(port, baudrate, IO_URL)
                    print(f"[SYSTEM] Loaded ice machine handler for '{brand}'")
                except Exception as e:
                    print(f"[SYSTEM][ERROR] Real Ice Driver Load Failed: {e}. Fallback to Mock.")
                    ice_machine_handler = MockIceMachine(port, baudrate, IO_URL)

    except FileNotFoundError:
        print("[SYSTEM][FATAL] 'config.json' not found. Cannot initialize devices.")
    except Exception as e:
        print(f"[SYSTEM][FATAL] Failed to load device handlers: {e}")

# ---- 공용 IO 함수 ----
def _io_pulse(unit, addr, duration):
    if SIMULATION_MODE:
        print(f"[MOCK IO] Pulse Unit={unit} Addr={addr} Duration={duration}")
        time.sleep(float(duration))
        return True
        
    try:
        r = requests.get(f"{IO_URL}/coil/pulse/{unit}/{addr}/{duration}", timeout=180.0)
        return r.status_code == 200
    except Exception as e:
        print('[ERR] io_pulse:', e)
        return False

def _io_pulse_index(unit, base, index, duration):
    addr = base + (index - 1)
    return _io_pulse(unit, addr, duration)

# ---- API Endpoints ----

@app.route('/coffee/<int:product_id>/<string:duration>', methods=['GET'])
def coffee(product_id, duration):
    print(f"[Device Service] Received coffee request: product_id={product_id}, duration={duration}")
    global coffee_status
    if not coffee_machine_handler:
        print("[Device Service] ERROR: Coffee machine not initialized!")
        return "Coffee machine not initialized", 503
    
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        print(f"[Device Service] ERROR: Invalid duration: {duration}")
        return 'BAD_PARAM: duration must be a number', 400

    if product_id <= 0:
        print(f"[Device Service] ERROR: Invalid product_id: {product_id}")
        return 'BAD_PARAM', 400

    print(f"[Device Service] Calling coffee_machine_handler.make_coffee({product_id}, {duration})")
    coffee_status = 1
    try:
        ok, msg = coffee_machine_handler.make_coffee(product_id, duration)
        print(f"[Device Service] Coffee result: ok={ok}, msg={msg}")
        
        if ok:
            return "OK", 200
        else:
            return f"FAIL: {msg}", 500
    finally:
        coffee_status = 0

@app.route('/coffee/rinse', methods=['GET'])
def coffee_rinse():
    """커피 머신 강제 헹굼을 시작합니다."""
    global coffee_machine_handler, coffee_status
    if not coffee_machine_handler:
        return "Coffee machine not initialized", 503

    print("[Device Service] Received force rinse request.")
    coffee_status = 1
    try:
        ok, msg = coffee_machine_handler.execute_rinse()
        if ok:
            return "OK", 200
        else:
            return f"FAIL: {msg}", 500
    except Exception as e:
        print(f"[Device Service][ERR] Exception during rinse: {e}")
        return f"FAIL: {e}", 500
    finally:
        coffee_status = 0

@app.route('/coffee/status', methods=['GET'])
def coffee_status_api():
    return jsonify({'status': coffee_status})

@app.route('/waterice/<string:ice>/<string:water>', methods=['GET'])
def water_ice(ice, water):
    print("=================== waterice : ", ice," / ",water, " ===============================")
    if not ice_machine_handler:
        return "Ice machine not initialized", 503
    
    try:
        ice = float(ice)
        water = float(water)
    except (ValueError, TypeError):
        return 'BAD_PARAM: ice/water must be numbers', 400

    # 1. 시리얼 통신으로 양 전송
    ok, message = ice_machine_handler.make_ice_water(ice, water)
    if not ok:
        return (message, 500)

    # 2. 버튼 누름 (DO 5:3200) 
    # 토출 시간 = max(ice, water) + 0.5 (Safety margin)
    #press_duration = max(ice, water) + 0.5
    press_duration = 0.5

    if press_duration > 0:
        btn_ok = _io_pulse(UNIT_ICEMACHINE_BTN, ADDR_ICEMACHINE_BTN, press_duration)
        if not btn_ok:
             return ('FAIL: Button trigger failed', 500)

    return ('OK', 200)

@app.route('/hotwater/<string:duration>', methods=['GET'])
def hotwater(duration):
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        return 'BAD_PARAM: duration must be a number', 400
    if duration <= 0: return 'BAD_PARAM', 400

    # 1. 시작 pulse
    ok_start = _io_pulse(UNIT_HOTWATER, ADDR_HOTWATER, 0.5)
    if not ok_start:
        return ('FAIL: start pulse', 500)

    # # 2. 온수 추출 시간 대기
    # time.sleep(duration)

    # # 3. 종료 pulse
    # ok_stop = _io_pulse(UNIT_HOTWATER, ADDR_HOTWATER, 0.5)
    # if not ok_stop:
    #     return ('FAIL: stop pulse', 500)

    return ('OK', 200)

@app.route('/sparkling/<string:duration>', methods=['GET'])
def sparkling(duration):
    print("=================== sparkling : ", duration, "===============================")
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        return 'BAD_PARAM: duration must be a number', 400
    if duration <= 0: return 'BAD_PARAM', 400
    ok = _io_pulse(UNIT_SPARKLING, ADDR_SPARKLING, duration)
    return ('OK', 200) if ok else ('FAIL', 500)

@app.route('/syrup/<int:code>/<string:duration>', methods=['GET'])
def syrup(code, duration):
    # code: 1~8 (Syrup ID)
    # 1~4 -> Syrup 1 Unit (ADDR_SYRUP_1_BASE)
    # 5~8 -> Syrup 2 Unit (ADDR_SYRUP_2_BASE)
    print("=================== syrup : ", code," / ",duration, " ===============================")
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        return 'BAD_PARAM: duration must be a number', 400
    if code <= 0 or duration <= 0: return 'BAD_PARAM', 400
    
    if code <= 4:
        # Syrup 1: Index 1~4
        base = ADDR_SYRUP_1_BASE
        idx = code
    else:
        # Syrup 2: Index 1~4 (Input 5~8)
        base = ADDR_SYRUP_2_BASE
        idx = code - 4

    ok = _io_pulse_index(UNIT_SYRUP, base, idx, duration)
    return ('OK', 200) if ok else ('FAIL', 500)

if __name__ == '__main__':
    # Flask 앱 실행 전 장비 핸들러 로드
    load_device_handlers()
    app.run(host='0.0.0.0', port=8500, threaded=True)

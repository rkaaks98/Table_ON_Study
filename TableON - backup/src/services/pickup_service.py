"""
Pickup Service - 고객 픽업대 관리
================================
- 픽업대 1개 (Zone 1) - Arduino
- DID 화면 연동 (REST API Polling 방식)
"""

from flask import Flask, request, jsonify, render_template
import threading, time, requests, json, os
from flask_cors import CORS

app = Flask(__name__, template_folder='../../web/templates', static_folder='../../web/static')
CORS(app, resources={r"/*": {"origins": "*"}})

# Node-RED Notify URL
NODERED_URL = "http://localhost:1880/notify"

def notify_clients(event_name, data=None):
    """Helper to send HTTP Trigger to Node-RED"""
    payload = {'event': event_name}
    if data:
        payload.update(data)
    
    def _send():
        try:
            requests.post(NODERED_URL, json=payload, timeout=0.5)
        except:
            pass
            
    threading.Thread(target=_send, daemon=True).start()

# Load Configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json')
RECIPE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'recipe.json')
SIMULATION_MODE = True
RECIPE_MAP = {}

def load_recipes():
    global RECIPE_MAP
    try:
        with open(RECIPE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    RECIPE_MAP[item['menu_code']] = item.get('menu_name', f"Menu {item['menu_code']}")
            elif isinstance(data, dict):
                for code, item in data.items():
                    RECIPE_MAP[int(code)] = item.get('menu_name', f"Menu {code}")
            
            print(f"[Pickup] Loaded {len(RECIPE_MAP)} recipes.")
    except Exception as e:
        print(f"[Pickup] Failed to load recipes: {e}")

try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
        SIMULATION_MODE = config.get('simulation_mode', True)
        print(f"[Pickup] Simulation Mode: {SIMULATION_MODE}")
except Exception as e:
    print(f"[Pickup] Failed to load config: {e}. Defaulting to Simulation Mode.")

load_recipes()

# ==== 픽업대 상태 (1개) ====
DIDArr = [[0, 0, 0, 0],  # 주문번호 (4 slots)
          [0, 0, 0, 0]]  # 메뉴코드
pickupStatus = [0, 0, 0, 0]
sensorValues = [0, 0, 0, 0]
ledControl = [0, 0, 0, 0]
sensorOffTime = [0, 0, 0, 0]

voice_flag = 0

# ==== IO 서버 연동 설정 ====
IO_URL = "http://localhost:8400"
session = requests.Session()

# ---- 내부 유틸 ----
def get_menu_name(code):
    return RECIPE_MAP.get(code, f"메뉴 {code}")

def build_did_json(zone_id=1):
    return {
        'zone': zone_id,
        'billNum01': DIDArr[0][0],
        'billNum02': DIDArr[0][1],
        'billNum03': DIDArr[0][2],
        'billNum04': DIDArr[0][3],
        'menuCode01': DIDArr[1][0],
        'menuCode02': DIDArr[1][1],
        'menuCode03': DIDArr[1][2],
        'menuCode04': DIDArr[1][3],
        'menuName01': get_menu_name(DIDArr[1][0]) if DIDArr[1][0] > 0 else "",
        'menuName02': get_menu_name(DIDArr[1][1]) if DIDArr[1][1] > 0 else "",
        'menuName03': get_menu_name(DIDArr[1][2]) if DIDArr[1][2] > 0 else "",
        'menuName04': get_menu_name(DIDArr[1][3]) if DIDArr[1][3] > 0 else "",
        'voice_flag': voice_flag
    }

# ---- IO 호출 헬퍼 (Arduino) ----
def io_read_arduino(pickup_id=1):
    try:
        url = f"{IO_URL}/arduino/sensor/{pickup_id}"
        r = session.get(url, timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) >= 4:
                return data[:4]
    except Exception as e:
        pass
    return None

# ---- DID 갱신 로직 ----
last_did_json = None

def update_did_logic(zone_id, index, order_num, menu_code):
    global last_did_json
    
    # zone_id는 하위 호환성을 위해 받지만, 항상 픽업대 1개로 처리
    max_idx = 4

    if 1 <= index <= max_idx:
        DIDArr[0][index-1] = order_num
        DIDArr[1][index-1] = menu_code

        if order_num != 0:
            pickupStatus[index-1] = 1
            ledControl[index-1] = 1
            sensorValues[index-1] = 1
        else:
            pickupStatus[index-1] = 0
            ledControl[index-1] = 0

    current_json = build_did_json()
    
    if last_did_json != current_json:
        last_did_json = current_json
        notify_clients('pickup_updated', {'zone': 1})

# ---- Flask 라우팅 ----

@app.route('/did')
def did_screen():
    """DID Screen (픽업대 1개)"""
    return render_template('DID.html', zone='pickup', zone_id=1)

@app.route('/updateDID/<int:zone>/<int:index>/<int:order_num>/<int:menu_code>', methods=['GET'])
def update_did(zone, index, order_num, menu_code):
    update_did_logic(zone, index, order_num, menu_code)
    return jsonify({'message': f'DID updated for Slot {index}'})

@app.route('/getDIDData/<int:zone>', methods=['GET'])
@app.route('/getDIDData', methods=['GET'])
def getDIDData(zone=1):
    retJson = build_did_json(zone)
    return jsonify(retJson)

@app.route('/getPickupStatus/<int:zone>', methods=['GET'])
@app.route('/getPickupStatus', methods=['GET'])
def getPickupStatus(zone=1):
    """Return occupancy status for scheduler (1=Occupied, 0=Empty)"""
    status = []
    for i in range(len(pickupStatus)):
        # 1이 비어있는 상태이므로, 0일 때를 Occupied로 판단해야 함
        is_occupied = 1 if (pickupStatus[i] == 1 or sensorValues[i] == 0) else 0
        status.append(is_occupied)
        
    return jsonify({'zone': 1, 'status': status})

@app.route('/resetAll', methods=['POST', 'GET'])
def reset_all_status():
    """픽업대 논리 상태 초기화 (수동 모드 전환 시 호출)"""
    global DIDArr, pickupStatus, ledControl
    
    DIDArr = [[0, 0, 0, 0], [0, 0, 0, 0]]
    pickupStatus = [0, 0, 0, 0]
    ledControl = [0, 0, 0, 0]
    
    notify_clients('pickup_updated', {'zone': 1})
    
    return jsonify({'message': 'Pickup status reset completed'})

@app.route('/getAllPickupStatus', methods=['GET'])
def get_all_pickup_status():
    """픽업대 상태 조회"""
    return jsonify({
        'pickup': {
            'status': pickupStatus,
            'sensors': sensorValues,
            'did': DIDArr
        }
    })

@app.route('/clearSlot/<int:zone>/<int:slot>', methods=['GET', 'POST'])
@app.route('/clearSlot/<int:slot>', methods=['GET', 'POST'])
def clear_slot(zone=1, slot=None):
    """특정 슬롯 강제 클리어"""
    if slot is None:
        slot = zone
        zone = 1
    update_did_logic(zone, slot, 0, 0)
    return jsonify({'message': f'Slot {slot} cleared'})

# ---- 폴링 쓰레드 ----
POLL_INTERVAL = 2  # 폴링 주기 (초) - RS485 버퍼 오버플로우 방지

def poll_loop():
    while True:
        try:
            # 픽업대 Arduino 폴링
            val = io_read_arduino(1)
            if val is not None:
                check_sensor_logic(val)
            
            print(f"[Pickup][DEBUG] Sensors:{val}")
            
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(POLL_INTERVAL)

def check_sensor_logic(sensors):
    count = len(sensors)
    for i in range(count):
        current_val = sensors[i]

        # Update Global Sensor Value
        sensorValues[i] = current_val
        
        if current_val == 1:  # Empty (사용자 확인 결과 1이 비어있음)
            if sensorOffTime[i] == 0:
                sensorOffTime[i] = time.time()
            elif time.time() - sensorOffTime[i] > 1.0:  # Debounce 1s
                # Cup removed -> Clear DID
                if pickupStatus[i] == 1:
                    update_did_logic(1, i+1, 0, 0)
        else:  # Cup Present (0)
            sensorOffTime[i] = 0

# 폴링 시작
threading.Thread(target=poll_loop, daemon=True).start()

if __name__ == '__main__':
    print("[PickupService] Starting (Polling Mode) on port 8600...")
    app.run(host='0.0.0.0', port=8600, debug=False, threaded=True)

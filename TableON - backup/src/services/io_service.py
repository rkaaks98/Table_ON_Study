# 04_io_server.py  — PURE IO SERVER (path-style endpoints + per-call unit + multi-unit read)
# 목적: 장비 의미 제거. coil/reg READ/WRITE/PULSE만 제공.
# 특징:
#  - 모든 엔드포인트에 unit을 경로 파라미터로 명시(예: /coil/write/<unit>/<addr>/<value>)
#  - 같은 "read" 안에서도 서로 다른 unit을 다뤄야 할 때를 위해 readMulti 제공
#  - 임시 호환: ENABLE_COMPAT=True 시 구 엔드포인트 일부 유지(추후 제거)

from flask import Flask, jsonify, request
import threading, time
import json, os
import serial  # Added for Arduino

app = Flask(__name__)

# ===== Modbus RTU / Simulation Config =====
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json')
SIMULATION_MODE = False
client = None
lock = threading.Lock()
arduino_readers = {}

# [Simulation State] Unit:Addr -> Value (0 or 1)
mock_sensor_state = {} 

class ArduinoReader:
    def __init__(self, pickup_id, port, baudrate, simulation=False):
        self.pickup_id = pickup_id
        self.port = port
        self.baudrate = baudrate
        self.simulation = simulation
        self.lock = threading.Lock()
        
        # Simulation State
        self.mock_data = [0, 0, 0, 0]

        print(f"[Arduino-{self.pickup_id}] Initialized (Port: {self.port}, Sim: {self.simulation})")

    def get_data(self):
        """요청 시 'S' 전송 -> 응답 수신 (매번 연결/해제 방식)"""
        if self.simulation:
            return list(self.mock_data)

        with self.lock:
            ser = None
            try:
                # 1. 연결 (DTR 비활성화로 Arduino 리셋 방지)
                ser = serial.Serial(
                    self.port, 
                    self.baudrate, 
                    timeout=1.0,
                    dsrdtr=False,
                    rtscts=False
                )
                ser.dtr = False
                time.sleep(0.1)  # 짧은 안정화 대기
                
                # 2. 버퍼 비우기
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # 3. 요청 전송 ('S')
                ser.write(b'S')
                
                # 4. 응답 대기 (ReadLine)
                line = ser.readline()
                
                # 5. 연결 해제
                ser.close()
                
                if not line:
                    return None
                
                line_str = line.decode(errors='ignore').strip()
                # Data format: "1,0,1,0"
                parts = line_str.split(',')
                if len(parts) >= 4:
                    # 값 반전: 1->0, 0->1 (센서: 1=비어있음 → 0=비어있음)
                    raw = [int(p) for p in parts[:4]]
                    inverted = [1 - v for v in raw]
                    return inverted
                
            except Exception as e:
                print(f"[Arduino-{self.pickup_id}] IO Error: {e}")
                if ser:
                    try:
                        ser.close()
                    except:
                        pass
        
        return None # 실패

    def send_led_command(self, index, command):
        pass

    # Method to manually set data (Simulation only)
    def set_mock_data(self, data):
        if self.simulation:
            with self.lock:
                self.mock_data = data
                print(f"[Arduino-{self.pickup_id}] Mock Data Set: {self.mock_data}")
                
            try:
                _print_sim_state()
            except: pass

# --- Simulation Control: Arduino ---
@app.route('/sim/setArduino/<int:pickup_id>/<int:v1>/<int:v2>/<int:v3>/<int:v4>', methods=['GET'])
def sim_set_arduino(pickup_id, v1, v2, v3, v4):
    if not SIMULATION_MODE:
        return jsonify({'error': 'Simulation Mode Only'}), 403
    
    reader = arduino_readers.get(pickup_id)
    if reader:
        reader.set_mock_data([v1, v2, v3, v4])
        return jsonify({'message': 'OK', 'id': pickup_id, 'data': [v1, v2, v3, v4]})
    return jsonify({'error': 'Reader not found'}), 404

def load_config():
    global SIMULATION_MODE, client, arduino_readers
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        SIMULATION_MODE = config.get('simulation_mode', False)
        print(f"[IO] Simulation Mode: {SIMULATION_MODE}")
        
        # 1. Modbus Init
        if not SIMULATION_MODE:
            #from pymodbus.client import ModbusSerialClient as ModbusClient
            from pymodbus.client.sync import ModbusSerialClient as ModbusClient
            client = ModbusClient(method='rtu', port='/dev/ttyUSB485', timeout=1, baudrate=57600)
            
        # 2. Arduino Init
        arduino_conf = config.get('arduino', {})
        # pickup_1 -> ID 1, pickup_2 -> ID 2
        for key, val in arduino_conf.items():
            if key == 'pickup_1':
                arduino_readers[1] = ArduinoReader(1, val['port'], val['baudrate'], SIMULATION_MODE)
            elif key == 'pickup_2':
                arduino_readers[2] = ArduinoReader(2, val['port'], val['baudrate'], SIMULATION_MODE)

    except Exception as e:
        print(f"[IO] Config/Init Error: {e}")
        pass

load_config()

# ===== (선택) 임시 호환 레이어 =====
ENABLE_COMPAT = True
ADDR_LED_BASE = 3204   # 예시, 필요 시 현장값으로 조정

# ===== 공용 유틸 =====

def _to_int(v, d=0):
    try:
        return int(v)
    except:
        return d


def _to_float(v, d=0.0):
    try:
        return float(v)
    except:
        return d


# ===== 내부 I/O 함수 =====

def _write_coil(addr, value, unit):
    if SIMULATION_MODE:
        print(f"[MOCK IO] write_coil unit={unit} addr={addr} value={value}")
        return True
        
    try:
        with lock:
            client.connect()
            client.write_coil(addr, bool(value), unit=unit)
            client.close()
        print(f"[IO] write_coil unit={unit} addr={addr} value={value}")
        return True
    except Exception as e:
        print("[ERR] write_coil:", e)
        try:
            client.close()
        except:
            pass
        return False


def _pulse_coil(addr, sec, unit):
    if SIMULATION_MODE:
        print(f"[MOCK IO] pulse_coil unit={unit} addr={addr} sec={sec}")
        time.sleep(float(sec))
        return True

    sec = max(0.0, float(sec))
    if sec == 0:
        return _write_coil(addr, False, unit=unit)
    ok = _write_coil(addr, True, unit=unit)
    if not ok:
        return False
    time.sleep(sec)
    return _write_coil(addr, False, unit=unit)


def _write_reg(addr, value, unit):
    if SIMULATION_MODE:
        print(f"[MOCK IO] write_reg unit={unit} addr={addr} value={value}")
        return True

    try:
        with lock:
            client.connect()
            client.write_register(addr, _to_int(value), unit=unit)
            client.close()
        print(f"[IO] write_reg unit={unit} addr={addr} value={value}")
        return True
    except Exception as e:
        print("[ERR] write_reg:", e)
        try:
            client.close()
        except:
            pass
        return False


def _read_bits(unit, addr, count, di=False):
    if SIMULATION_MODE:
        # Read from mock_sensor_state
        bits = []
        for i in range(count):
            target_addr = addr + i
            key = f"{unit}:{target_addr}"
            val = mock_sensor_state.get(key, 0)
            bits.append(val)
        # print(f"[MOCK IO] read_bits unit={unit} addr={addr} count={count} -> {bits}")
        return bits

    try:
        with lock:
            client.connect()
            res = client.read_discrete_inputs(addr, count, unit=unit) if di else client.read_coils(addr, count, unit=unit)
            client.close()
        if hasattr(res, 'isError') and res.isError():
            return None
        bits = [int(res.bits[i]) for i in range(count)]
        print(f"[IO] read_{'di' if di else 'coils'} unit={unit} addr={addr} count={count} -> {bits}")
        return bits
    except Exception as e:
        print("[ERR] read_bits:", e)
        try:
            client.close()
        except:
            pass
        return None


def _read_regs(unit, addr, count, holding=True):
    if SIMULATION_MODE:
        return [0] * count

    try:
        with lock:
            client.connect()
            res = client.read_holding_registers(addr, count, unit=unit) if holding else client.read_input_registers(addr, count, unit=unit)
            client.close()
        if hasattr(res, 'isError') and res.isError():
            return None
        vals = [int(res.registers[i]) for i in range(count)]
        print(f"[IO] read_{'hr' if holding else 'ir'} unit={unit} addr={addr} count={count} -> {vals}")
        return vals
    except Exception as e:
        print("[ERR] read_regs:", e)
        try:
            client.close()
        except:
            pass
        return None


# ===== Multi-Unit 파서 =====
# spec 예: "5:0:4,3:100:1"  → [(unit=5, addr=0, count=4), (unit=3, addr=100, count=1)]

def _parse_multi_spec(spec: str):
    chunks = []
    if not spec:
        return chunks
    for token in spec.split(','):
        parts = token.split(':')
        if len(parts) != 3:
            continue
        u, a, c = _to_int(parts[0], None), _to_int(parts[1], None), _to_int(parts[2], None)
        if None in (u, a, c):
            continue
        chunks.append((u, a, c))
    return chunks


# ===== PURE IO Endpoints (모두 unit을 경로에 명시) =====

@app.route('/health', methods=['GET'])
def health():
    return 'OK'

# --- Arduino Sensor Read ---
@app.route('/arduino/sensor/<int:pickup_id>', methods=['GET'])
def arduino_sensor(pickup_id):
    reader = arduino_readers.get(pickup_id)
    if reader:
        data = reader.get_data()
        if data is not None:
            return jsonify(data)
        else:
            return jsonify({'error': 'Read Failed or Timeout'}), 500
            
    # If simulation mode and reader not found (e.g. config missing), return dummy
    if SIMULATION_MODE:
        return jsonify([0, 0, 0, 0])
    return jsonify({'error': 'Not Found'}), 404

# --- Arduino Sensor Set (Mock Only) ---
@app.route('/arduino/sensor/set/<int:pickup_id>/<int:v1>/<int:v2>/<int:v3>/<int:v4>', methods=['GET'])
def arduino_sensor_set(pickup_id, v1, v2, v3, v4):
    if not SIMULATION_MODE:
        return jsonify({'error': 'Simulation Mode Only'}), 403
    
    reader = arduino_readers.get(pickup_id)
    if reader:
        reader.set_mock_data([v1, v2, v3, v4])
        return jsonify({'message': 'Mock Data Updated', 'data': [v1, v2, v3, v4]})
    return jsonify({'error': 'Reader Not Found'}), 404

# --- Coil ---
@app.route('/coil/write/<int:unit>/<int:addr>/<int:value>', methods=['GET'])
def coil_write(unit, addr, value):
    ok = _write_coil(addr, value, unit)
    return ('OK', 200) if ok else ('FAIL', 500)

@app.route('/coil/pulse/<int:unit>/<int:addr>/<string:duration>', methods=['GET'])
def coil_pulse(unit, addr, duration):
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        return 'BAD_PARAM: duration must be a number', 400
    ok = _pulse_coil(addr, duration, unit)
    return ('OK', 200) if ok else ('FAIL', 500)

# base + index (addr = base + (index-1))
@app.route('/coil/pulseIndex/<int:unit>/<int:base>/<int:index>/<string:duration>', methods=['GET'])
def coil_pulse_index(unit, base, index, duration):
    addr = base + (index - 1)
    try:
        duration = float(duration)
    except (ValueError, TypeError):
        return 'BAD_PARAM: duration must be a number', 400
    ok = _pulse_coil(addr, duration, unit)
    return ('OK', 200) if ok else ('FAIL', 500)

# --- Coils/DI Read ---
@app.route('/coils/read/<int:unit>/<int:addr>/<int:count>', methods=['GET'])
def coils_read(unit, addr, count):
    bits = _read_bits(unit, addr, count, di=False)
    return (jsonify(bits), 200) if bits is not None else (jsonify({'error': 'read fail'}), 500)

@app.route('/di/read/<int:unit>/<int:addr>/<int:count>', methods=['GET'])
def di_read(unit, addr, count):
    bits = _read_bits(unit, addr, count, di=True)
    return (jsonify(bits), 200) if bits is not None else (jsonify({'error': 'read fail'}), 500)

# --- Registers ---
@app.route('/hr/write/<int:unit>/<int:addr>/<int:value>', methods=['GET'])
def hr_write(unit, addr, value):
    ok = _write_reg(addr, value, unit=unit)
    return ('OK', 200) if ok else ('FAIL', 500)

@app.route('/hr/read/<int:unit>/<int:addr>/<int:count>', methods=['GET'])
def hr_read(unit, addr, count):
    vals = _read_regs(unit, addr, count, holding=True)
    return (jsonify(vals), 200) if vals is not None else (jsonify({'error': 'read fail'}), 500)

@app.route('/ir/read/<int:unit>/<int:addr>/<int:count>', methods=['GET'])
def ir_read(unit, addr, count):
    vals = _read_regs(unit, addr, count, holding=False)
    return (jsonify(vals), 200) if vals is not None else (jsonify({'error': 'read fail'}), 500)

# --- Multi-Unit Reads ---
# coils/di/hr/ir 모두 동일 패턴의 readMulti 제공
@app.route('/coils/readMulti/<path:spec>', methods=['GET'])
@app.route('/di/readMulti/<path:spec>', methods=['GET'])
@app.route('/hr/readMulti/<path:spec>', methods=['GET'])
@app.route('/ir/readMulti/<path:spec>', methods=['GET'])
def read_multi(spec):
    chunks = _parse_multi_spec(spec)
    if not chunks:
        return jsonify({'error': 'BAD_SPEC'}), 400

    kind = request.path.split('/')[1]  # 'coils' | 'di' | 'hr' | 'ir'
    results = []
    flat = []

    for (u, a, c) in chunks:
        if kind == 'coils':
            data = _read_bits(u, a, c, di=False)
        elif kind == 'di':
            data = _read_bits(u, a, c, di=True)
        elif kind == 'hr':
            data = _read_regs(u, a, c, holding=True)
        else:
            data = _read_regs(u, a, c, holding=False)

        if data is None:
            results.append({'unit': u, 'addr': a, 'count': c, 'error': 'read fail'})
        else:
            results.append({'unit': u, 'addr': a, 'count': c, 'data': data})
            flat.extend(data)

    return jsonify({'chunks': results, 'flat': flat})

# --- Simulation Control ---
@app.route('/sim/setSensor/<int:unit>/<int:addr>/<int:value>', methods=['GET'])
def sim_set_sensor(unit, addr, value):
    if not SIMULATION_MODE:
        return jsonify({'error': 'Simulation Mode Only'}), 403
        
    key = f"{unit}:{addr}"
    mock_sensor_state[key] = 1 if value else 0
    
    # 현재 상태 출력
    print(f"[MOCK IO] Set Sensor {key} = {value}")
    # _print_sim_state() # 상태 변경 시 전체 출력
    
    return jsonify({'message': 'OK', 'key': key, 'value': value})

@app.route('/sim/getAllSensors', methods=['GET'])
def sim_get_all_sensors():
    """현재 시뮬레이션 센서 상태 전체 반환"""
    if not SIMULATION_MODE:
        return jsonify({'error': 'Simulation Mode Only'}), 403
        
    # Modbus Mock Data
    shared = [mock_sensor_state.get(f"3:{i}", 0) for i in range(4)]
    shot = [mock_sensor_state.get(f"4:{i}", 0) for i in range(4)]
    worker = [mock_sensor_state.get(f"4:{i}", 0) for i in range(4, 8)]
    
    # Arduino Mock Data
    arduino = {}
    for pid in [1, 2]:
        reader = arduino_readers.get(pid)
        if reader:
            arduino[f'pickup_{pid}'] = reader.get_data()
            
    return jsonify({
        'modbus': {
            'shared_jig': shared, # 0-3
            'shot_jig': shot,     # 4-7
            'worker_pickup': worker # 8-11
        },
        'arduino': arduino
    })

# --- Simulation Helpers (Moved from pickup_service) ---
@app.route('/sim/setShotJig/<int:slot>/<int:state>', methods=['GET'])
def sim_set_shot_jig(slot, state):
    """Shot Jig Sensor (Unit 4, Addr 0~3)"""
    if not (1 <= slot <= 4): return jsonify({'error': 'Invalid slot'}), 400
    addr = 0 + (slot - 1)
    mock_sensor_state[f"4:{addr}"] = 1 if state else 0
    return jsonify({'message': 'OK', 'slot': slot, 'state': state})

@app.route('/sim/setShotJigAll/<int:state>', methods=['GET'])
def sim_set_shot_jig_all(state):
    """Set All Shot Jig Sensors (Unit 4, Addr 0~3)"""
    val = 1 if state else 0
    for i in range(4):
        mock_sensor_state[f"4:{i}"] = val
    return jsonify({'message': 'OK', 'state': val})

@app.route('/sim/setCoopJig/<int:slot>/<int:state>', methods=['GET'])
def sim_set_coop_jig(slot, state):
    """Worker Pickup Sensor (Unit 4, Addr 4~7)"""
    if not (1 <= slot <= 4): return jsonify({'error': 'Invalid slot'}), 400
    addr = 4 + (slot - 1)
    mock_sensor_state[f"4:{addr}"] = 1 if state else 0
    return jsonify({'message': 'OK', 'slot': slot, 'state': state})

@app.route('/sim/setPickup/<int:zone>/<int:slot>/<int:state>', methods=['GET'])
def sim_set_pickup_helper(zone, slot, state):
    """Pickup Zone Sensor (Zone 0, 1, 2)"""
    # Zone 0: Worker Pickup (Unit 4, Addr 4~7)
    if zone == 0:
        if not (1 <= slot <= 4): return jsonify({'error': 'Invalid slot'}), 400
        addr = 4 + (slot - 1)
        # Simulation: Update mock state directly
        mock_sensor_state[f"4:{addr}"] = 1 if state else 0
        return jsonify({'message': 'OK', 'zone': 0, 'slot': slot, 'state': state})

    if zone not in [1, 2]: return jsonify({'error': 'Invalid zone'}), 400
    if not (1 <= slot <= 4): return jsonify({'error': 'Invalid slot'}), 400
    
    reader = arduino_readers.get(zone)
    if reader:
        # 현재 값 읽어서 해당 슬롯만 변경
        current = reader.get_data() # [s1, s2, s3]
        current[slot-1] = 1 if state else 0
        reader.set_mock_data(current)
        return jsonify({'message': 'OK', 'zone': zone, 'data': current})
    return jsonify({'error': 'Reader not found'}), 404

def _print_sim_state():
    """현재 시뮬레이션 센서 상태를 보기 좋게 출력 (Thread-Safe with internal Copy)"""
    
    # Snapshot data to avoid holding locks during print
    shared = [mock_sensor_state.get(f"3:{i}", 0) for i in range(4)]
    shot = [mock_sensor_state.get(f"4:{i}", 0) for i in range(4)]
    worker = [mock_sensor_state.get(f"4:{i}", 0) for i in range(4, 8)]
    
    arduino_data = {}
    for pid in [1, 2]:
        reader = arduino_readers.get(pid)
        if reader:
            arduino_data[pid] = reader.get_data() # get_data uses its own lock

    # Print without locks
    print("\n=== [SIMULATION SENSOR STATE] ===")
    print(f"  Shared Jig (Addr 0-3): {shared}")
    print(f"  Shot Jig   (Addr 4-7): {shot}")
    print(f"  Worker Pickup (Addr 8-11): {worker}")
    for pid, data in arduino_data.items():
        print(f"  Pickup Zone {pid} (Arduino): {data}")
    print("=================================\n")

# ===== 임시 호환 (장비 성격의 구 엔드포인트) — 추후 제거 =====
if ENABLE_COMPAT:
    @app.route('/setLED/<int:index>/<int:value>', methods=['GET'])
    def set_led(index, value):
        addr = ADDR_LED_BASE + (index - 1)
        unit = _to_int(request.args.get('unit', 5), 5)
        ok = _write_coil(addr, value, unit=unit)
        return ('OK', 200) if ok else ('FAIL', 500)

    @app.route('/checkSensor', methods=['GET'])
    def check_sensor_compat():
        """
        호환용 센서 읽기:
        - Coils(출력 비트) 우선 읽기 → 실패 시 DI(입력 비트)로 폴백
        - 쿼리: ?unit=<id>&addr=<start>&count=<n>
        """
        addr = _to_int(request.args.get('addr', 0))
        count = _to_int(request.args.get('count', 4))
        unit = _to_int(request.args.get('unit', 3))

        # 1) COILS 먼저 (현장 배선이 Coils인 경우)
        bits = _read_bits(unit, addr, count, di=False)
        # 2) 실패 시 DI로 재시도 (일부 현장 DI 배선 대비)
        if bits is None:
            bits = _read_bits(unit, addr, count, di=True)

        if bits is None:
            return jsonify({'error': 'read fail'}), 500
        return jsonify(bits)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8400, debug=False, threaded=True)

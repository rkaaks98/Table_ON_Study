# devices/coffee_machine/thermoplan.py
import json
import serial
import time
import threading
import argparse
import os
try:
    # 생성된 protobuf 모듈을 임포트합니다.
    import thermoplanAPI as api_pb2
except ImportError:
    # VSCode와 같은 환경에서 모듈을 직접 찾지 못할 경우를 대비하여
    # 현재 파일의 디렉토리를 sys.path에 추가합니다.
    import sys
    sys.path.append(os.path.dirname(__file__))
    import thermoplanAPI as api_pb2

# --- 프로토콜 상수 (coffee.py 참조) ---
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text
DLE = 0x10  # Data Link Escape (참고용)

class ThermoplanCoffeeMachine:
    """
    Thermoplan 커피 머신과의 시리얼 통신을 관리하는 클래스.
    통신 시점에 포트를 열고 닫는 방식으로 안정성을 확보합니다.
    """
    def __init__(self, port, baudrate=115200):
        """
        커피 머신 핸들러를 초기화합니다.
        시리얼 포트는 통신 시점에 열고 닫습니다.
        """
        self.port = port
        self.baudrate = baudrate
        self.sequence_id = 0
        self.lock = threading.Lock()
        self.product_map = {}

        try:
            # config.json 파일의 절대경로
            config_path = '/home/TableON/config/config.json' # 경로를 변수로 먼저 선언
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.product_map = config.get('coffee_machine', {}).get('thermoplan_product_map', {})
            print(f"[Coffee] Loaded Thermoplan product map: {self.product_map}")
        except Exception as e:
            # 에러 발생 시 어떤 경로에서 어떤 에러가 났는지 명확히 출력
            print(f"[Coffee][FATAL] Could not load or parse config.json from '{config_path}': {e}")
            # self.product_map은 빈 dict {}로 유지됩니다.

    def _get_next_sequence_id(self):
        """호출 시마다 1씩 증가하는 스레드 안전한 시퀀스 ID를 반환합니다."""
        with self.lock:
            self.sequence_id += 1
            return self.sequence_id

    def _execute_command(self, request_message: api_pb2.ApiMessage, response_timeout=5.0):
        """
        시리얼 포트를 열고, 명령을 보내고, 응답을 받고, 포트를 닫는 전체 과정을 관리합니다.
        이 함수는 스레드에 안전합니다.
        """
        MAX_RETRIES = 3
        
        for attempt in range(MAX_RETRIES):
            with self.lock:
                ser = None
                try:
                    # 1. 시리얼 포트 열기 (RTS/DTR 비활성화로 I/O 에러 방지)
                    ser = serial.Serial(
                        self.port, 
                        self.baudrate, 
                        timeout=1,
                        rtscts=False,
                        dsrdtr=False
                    )
                    
                    # 2. 요청 전송
                    ok, msg = self._send_request(ser, request_message)
                    if not ok:
                        return None, msg

                    # 3. 응답 수신
                    return self._receive_response(ser, timeout=response_timeout)

                except (serial.SerialException, OSError) as e:
                    print(f"[Coffee] Serial error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(0.5)  # 재시도 전 대기
                        continue
                    print(f"[Coffee][FATAL] All retries failed")
                    return None, str(e)
                finally:
                    # 4. 시리얼 포트 닫기
                    if ser and ser.is_open:
                        try:
                            ser.close()
                        except:
                            pass
        
        return None, "Max retries exceeded"

    # =============================================
    # --- 핵심 통신 로직 (내부 헬퍼 함수) ---
    # =============================================

    def _crc16(self, message: bytes) -> int:
        """CRC-16 계산"""
        polynom = 0xC86C
        crc = 0xFFFF
        for byte in message:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ polynom
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    def _apply_custom_transformation(self, data: bytes) -> bytes:
        """이스케이프 처리"""
        transformed_data = bytearray()
        for byte in data:
            if byte == 0x10:
                transformed_data.extend([0x10, 0x30])
            elif byte == 0x02:
                transformed_data.extend([0x10, 0x22])
            elif byte == 0x03:
                transformed_data.extend([0x10, 0x23])
            else:
                transformed_data.append(byte)
        return bytes(transformed_data)

    def _finalize_message(self, data: bytes) -> bytes:
        """STX, ETX 추가"""
        return bytes([STX]) + data + bytes([ETX])

    def _send_request(self, ser: serial.Serial, request: api_pb2.ApiMessage):
        """Protobuf 요청을 전송 가능한 바이트 스트림으로 변환하여 전송"""
        ser.reset_input_buffer()
        
        message = bytearray(request.SerializeToString())
        crc = self._crc16(message)
        message.append((crc >> 8) & 0xFF)
        message.append(crc & 0xFF)

        transformed = self._apply_custom_transformation(message)
        final_message = self._finalize_message(transformed)

        try:
            ser.write(final_message)
            return True, "Command sent"
        except serial.SerialException as e:
            print(f"[Coffee][ERR] Failed to write to serial port: {e}")
            return False, str(e)

    def _reverse_custom_transformation(self, data: bytes) -> bytes:
        """이스케이프된 값 복원"""
        i = 0
        restored_data = bytearray()
        while i < len(data):
            if data[i] == 0x10 and i + 1 < len(data):
                if data[i+1] == 0x30: restored_data.append(0x10)
                elif data[i+1] == 0x22: restored_data.append(0x02)
                elif data[i+1] == 0x23: restored_data.append(0x03)
                else: restored_data.extend(data[i:i+2])
                i += 1
            else:
                restored_data.append(data[i])
            i += 1
        return bytes(restored_data)

    def _receive_response(self, ser: serial.Serial, timeout=5.0):
        """머신으로부터 응답을 수신하고 파싱"""
        raw_response = bytearray()
        start_time = time.time()
        
        stx_found = False
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                byte = ser.read(1)
                if byte == bytes([STX]):
                    stx_found = True
                    break
        if not stx_found: return None, "STX not found"

        in_escape = False
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                byte = ser.read(1)
                raw_response.extend(byte)
                if byte == bytes([ETX]) and not in_escape: break
                in_escape = byte == bytes([DLE]) and not in_escape
        
        if not raw_response.endswith(bytes([ETX])): return None, "No ETX or timeout"

        framed_data = raw_response[:-1]
        transformed_data = self._reverse_custom_transformation(framed_data)

        if len(transformed_data) < 2: return None, "Response too short"

        received_crc = (transformed_data[-2] << 8) | transformed_data[-1]
        payload = transformed_data[:-2]
        calculated_crc = self._crc16(payload)

        if received_crc != calculated_crc:
            return None, f"CRC mismatch! Recv: {received_crc:04x}, Calc: {calculated_crc:04x}"

        try:
            response_message = api_pb2.ApiMessage()
            response_message.ParseFromString(payload)
            return response_message, "Success"
        except Exception as e:
            return None, f"Protobuf parsing error: {e}"

    # =============================================
    # --- 공개 API 메소드 ---
    # =============================================
    def _create_base_request(self):
        """공통 시퀀스 ID를 포함하는 기본 요청 객체 생성"""
        req = api_pb2.ApiMessage()
        req.sequence_id = self._get_next_sequence_id()
        return req

    def make_coffee(self, product_id: int, duration: float):
        """커피 제조 (device_service에서 호출)"""
        product_id_str = self.product_map.get(str(product_id))
        if not product_id_str:
            err_msg = f"UNKNOWN PRODUCT ID: No mapping for ID {product_id} in config."
            print(f"[Thermoplan][ERR] {err_msg}")
            return False, err_msg

        print(f"[Thermoplan] Making coffee: ID {product_id} -> '{product_id_str}', Duration={duration}s")

        request = self._create_base_request()
        request.start_product.product_id = product_id_str
        request.start_product.start_delay_s = 0.0

        response, status = self._execute_command(request, response_timeout=5.0)
        if not response:
            return False, f"No valid response after starting product: {status}"

        if not response.HasField("product_started"):
            return False, f"Received unexpected response type: {response}"

        print(f"[Thermoplan] Waiting for extraction duration: {duration}s")
        time.sleep(duration)
        
        print(f"[Thermoplan] Coffee making process for '{product_id_str}' completed.")
        return True, "Successfully started and waited for coffee"

    def execute_rinse(self):
        """강제 헹굼"""
        request = self._create_base_request()
        request.force_rinse.SetInParent()

        response, status = self._execute_command(request, response_timeout=10.0)
        if not response:
            return False, f"No valid response after rinse command: {status}"

        print(f"[Thermoplan] Rinse command acknowledged with response: {response}")
        return True, "Rinse command acknowledged."

    def start_product(self, product_id: str, delay_sec: float = 0.0):
        """제품 추출 시작"""
        request = self._create_base_request()
        request.start_product.product_id = product_id
        request.start_product.start_delay_s = delay_sec
        return self._execute_command(request)

    def cancel_product(self, product_id: str, delay_sec: float = 0.0):
        """제품 추출 취소"""
        request = self._create_base_request()
        request.cancel_product.product_id = product_id
        request.cancel_product.cancel_delay_s = delay_sec
        return self._execute_command(request)

    def get_product_list(self):
        """사용 가능한 제품 목록 요청"""
        request = self._create_base_request()
        request.get_product_list.SetInParent()
        return self._execute_command(request)

    def get_available_product_ids(self):
        request = self._create_base_request()
        request.get_available_product_ids.SetInParent()
        return self._execute_command(request)

    def get_active_events(self):
        request = self._create_base_request()
        request.get_active_events.SetInParent()
        return self._execute_command(request)

    def force_rinse(self):
        request = self._create_base_request()
        request.force_rinse.SetInParent()
        return self._execute_command(request)

    def postpone_rinse(self, milliseconds: int):
        request = self._create_base_request()
        request.postpone_rinse.milliseconds = milliseconds
        request.postpone_rinse.SetInParent()
        return self._execute_command(request)

    def get_sw_version(self):
        request = self._create_base_request()
        request.get_sw_version.SetInParent()
        return self._execute_command(request)

    def get_nsf_compliant_cleaning(self):
        request = self._create_base_request()
        request.get_nsf_compliant_cleaning.SetInParent()
        return self._execute_command(request)


if __name__ == '__main__':
    # --- 터미널에서 직접 실행을 위한 CLI 설정 ---
    parser = argparse.ArgumentParser(description="Thermoplan Coffee Machine CLI Tool")
    parser.add_argument("--port", type=str, default="/dev/ttyUSBCoffee", help="Serial port (default: /dev/ttyUSBCoffee)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baudrate (default: 115200)")

    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    # 각 기능별 서브-파서 추가
    subparsers.add_parser("get_list", help="Get product list")
    subparsers.add_parser("get_available_ids", help="Get available product IDs")
    subparsers.add_parser("get_events", help="Get active events")
    subparsers.add_parser("get_version", help="Get software version")
    subparsers.add_parser("get_nsf", help="Get NSF compliant cleaning status")
    subparsers.add_parser("rinse", help="Force rinse")

    start_parser = subparsers.add_parser("start", help="Start making a product")
    start_parser.add_argument("--id", type=str, required=True, help="Product ID (e.g., 'Double Espresso_1')")
    start_parser.add_argument("--delay", type=float, default=0.0, help="Start delay in seconds")

    cancel_parser = subparsers.add_parser("cancel", help="Cancel a product")
    cancel_parser.add_argument("--id", type=str, required=True, help="Product ID to cancel")
    cancel_parser.add_argument("--delay", type=float, default=0.0, help="Cancel delay in seconds")

    postpone_parser = subparsers.add_parser("postpone", help="Postpone rinse")
    postpone_parser.add_argument("--ms", type=int, required=True, help="Milliseconds to postpone")

    make_parser = subparsers.add_parser("make", help="Make a coffee product (sends start, waits, and checks response)")
    make_parser.add_argument("--id", type=int, required=True, help="Product ID (integer)")
    make_parser.add_argument("--duration", type=float, required=True, help="Extraction duration to wait in seconds")

    args = parser.parse_args()

    machine = ThermoplanCoffeeMachine(port=args.port, baudrate=args.baudrate)

    print(f"[CLI] Executing command '{args.command}' on {args.port}...")

    # 'make' 명령어는 자체적으로 응답 처리 로직을 포함
    if args.command == "make":
        ok, msg = machine.make_coffee(product_id=args.id, duration=args.duration)
        if ok:
            print(f"[CLI] 'make' command finished successfully: {msg}")
        else:
            print(f"[CLI][ERR] 'make' command failed: {msg}")
    else:
        response, status = None, "Command not implemented"
        if args.command == "get_list":
            response, status = machine.get_product_list()
        elif args.command == "get_available_ids":
            response, status = machine.get_available_product_ids()
        elif args.command == "get_events":
            response, status = machine.get_active_events()
        elif args.command == "get_version":
            response, status = machine.get_sw_version()
        elif args.command == "get_nsf":
            response, status = machine.get_nsf_compliant_cleaning()
        elif args.command == "rinse":
            response, status = machine.force_rinse()
        elif args.command == "start":
            response, status = machine.start_product(product_id=args.id, delay_sec=args.delay)
        elif args.command == "cancel":
            response, status = machine.cancel_product(product_id=args.id, delay_sec=args.delay)
        elif args.command == "postpone":
            response, status = machine.postpone_rinse(milliseconds=args.ms)

        if response:
            print("[CLI] Response received successfully.")
            # 응답 내용을 보기 좋게 출력
            try:
                from google.protobuf.json_format import MessageToDict
                import json
                print(json.dumps(MessageToDict(response, preserving_proto_field_name=True),
                                 ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"[CLI][WARN] Could not convert response to JSON: {e}")
                print(response)
        else:
            print(f"[CLI][ERR] Command failed: {status}")

    print("[CLI] Done.")
# devices/ice_machine/nakajo.py
import serial
import time
import requests

class NakajoIceMachine:
    def __init__(self, port, baudrate, io_url):
        self.port = port
        self.baudrate = baudrate
        self.io_url = io_url
        # Nakajo 제어를 위한 IO 보드 주소 (필요 시 config.json으로 이동 가능)
        self.unit_ice_switch = 5
        self.addr_ice_switch = 3200
        print(f"[Ice] Nakajo machine initialized at port {self.port}")

    def make_ice_water(self, ice_sec, water_sec):
        """Nakajo 장비로 얼음과 물을 배출합니다."""
        print(f"[Ice] Making ice/water with Nakajo: ice={ice_sec}, water={water_sec}")
        try:
            # 1. 시리얼 통신으로 제빙기에 얼음/물 준비 명령
            self._send_api(ice_sec, water_sec)
            time.sleep(0.3)

            # 2. IO서버를 통해 게이트를 열어 배출
            gate_open_duration = max(float(ice_sec), float(water_sec))
            self._open_gate(gate_open_duration)
            time.sleep(0.2)
            
            return True, "Nakajo water/ice done"
        except Exception as e:
            print(f"[Ice][ERR] Nakajo operation failed: {e}")
            return False, str(e)

    def _send_api(self, ice_time, water_time):
        """Nakajo 제빙기에 시리얼 명령을 전송합니다."""
        # Nakajo 프로토콜에 맞는 바이트 배열 생성
        api = bytearray(b'\x02\x01\xb0\x00\x00\x00\x03')
        api[3] = int(ice_time) * 16
        api[4] = int(water_time) * 16
        api[5] = self._xor_checksum(api[1], api[2], api[3], api[4])

        ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.3
        )
        try:
            ser.write(api)
        finally:
            ser.close()
        print(f'[Nakajo] API sent: ice={ice_time}, water={water_time}')

    def _xor_checksum(self, b1, b2, b3, b4):
        """API 전송에 필요한 체크섬을 계산합니다."""
        return (b1 ^ b2 ^ b3 ^ b4) & 0xFF

    def _open_gate(self, duration):
        """IO 서버를 호출하여 얼음/물 배출 게이트를 엽니다."""
        try:
            url = f"{self.io_url}/coil/pulse/{self.unit_ice_switch}/{self.addr_ice_switch}/{duration}"
            r = requests.get(url, timeout=180.0)
            return r.status_code == 200
        except Exception as e:
            print(f'[Ice][ERR] Failed to open gate via IO server: {e}')
            return False
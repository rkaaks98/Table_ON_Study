# coffee_machines/eversys.py
import serial
import os
import time
from . import eversysAPIList # eversysAPIList를 상대 경로로 임포트

class EversysCoffeeMachine:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        print(f"[Coffee] Eversys machine initialized at {self.port}")

    def make_coffee(self, product_num, duration):
        """Eversys 머신으로 커피를 제조합니다."""
        print(f"[Coffee] Making coffee with Eversys: product={product_num}, duration={duration}")
        try:
            self._send_api(product_num)
            time.sleep(duration)
            return True, "Eversys coffee done"
        except Exception as e:
            print(f"[Coffee][ERR] Eversys API call failed: {e}")
            return False, str(e)

    def _send_api(self, product_num):
        """Eversys API 데이터를 시리얼 포트로 전송합니다."""
        # PN.txt 파일 경로를 현재 파일(eversys.py)과 동일한 위치로 고정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pn_path = os.path.join(base_dir, 'PN.txt')

        if not os.path.exists(pn_path):
            with open(pn_path, 'w', encoding='utf-8') as f:
                f.write('0')
        with open(pn_path, 'r+', encoding='utf-8') as pnFile:
            raw = pnFile.read().strip()
            PN = int(raw) if raw.isdigit() else 0
            pnFile.seek(0); pnFile.write('1' if PN == 0 else '0'); pnFile.truncate()

        apiData = eversysAPIList.getAPI(int(product_num)-1, PN)
        
        ser = serial.Serial()
        ser.port = self.port
        ser.baudrate = self.baudrate
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.timeout = 0.3
        
        try:
            ser.open()
            ser.write(apiData)
        finally:
            ser.close()
        print(f'[Eversys] API sent, product={product_num}')

    def execute_rinse(self):
        """Eversys 머신 린싱을 수행합니다. (기본값: Rinse Left)"""
        print("[Coffee] Executing Eversys rinse...")
        try:
            # eversysAPIList.py에 정의된 인덱스 기준:
            # 17: rinse left
            # 18: rinse left milk outlet
            # 19: rinse screen left
            
            # 여기서는 기본적으로 'rinse left' (인덱스 17)를 수행합니다.
            # 필요에 따라 다른 린싱 모드를 선택할 수 있도록 수정 가능합니다.
            RINSE_INDEX = 17 
            
            self._send_api(RINSE_INDEX + 1) # _send_api는 (product_num - 1)을 하므로 +1 해서 전달
            
            # 린싱 소요 시간 대기 (약 10초로 가정, 필요시 조정)
            time.sleep(10)
            
            return True, "Eversys rinse started"
        except Exception as e:
            print(f"[Coffee][ERR] Eversys rinse failed: {e}")
            return False, str(e)
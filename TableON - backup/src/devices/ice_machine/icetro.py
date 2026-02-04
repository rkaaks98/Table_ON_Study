# devices/ice_machine/icetro.py
import serial
import time

class IcetroIceMachine:
    def __init__(self, port, baudrate, io_url=None):
        self.port = port
        self.baudrate = baudrate
        # io_url은 Nakajo와 인터페이스를 맞추기 위해 받지만, Icetro에서는 사용하지 않습니다.
        print(f"[Ice] Icetro machine initialized at port {self.port}")

    def make_ice_water(self, ice_sec, water_sec):
        """Icetro 장비로 얼음과 물을 배출합니다."""
        print(f"[Ice] Making ice/water with Icetro: ice={ice_sec}, water={water_sec}")
        try:
            # 1. 시리얼 통신으로 제빙기에 직접 토출 명령
            self._send_api(rst=0, water=water_sec, ice=ice_sec)
            
            # 2. 장비가 동작할 시간을 기다립니다.
            # Icetro는 명령 전송 후 바로 토출이 시작되므로, 레시피 시간만큼 대기합니다.
            operation_time = max(float(ice_sec), float(water_sec))
            #time.sleep(operation_time)
            time.sleep(0.5)

            # 3. (옵션) 제공된 코드의 로직에 따라 토출 후 리셋 명령을 보낼 수 있습니다.
            # self.reset()

            return True, "Icetro water/ice done"
        except Exception as e:
            print(f"[Ice][ERR] Icetro operation failed: {e}")
            return False, str(e)

    def reset(self):
        """Icetro 장비를 리셋합니다."""
        print("[Ice] Resetting Icetro machine.")
        try:
            self._send_api(rst=1, water=0, ice=0)
            return True
        except Exception as e:
            print(f"[Ice][ERR] Icetro reset failed: {e}")
            return False

    def _send_api(self, rst, water, ice):
        """Icetro 제빙기에 시리얼 명령을 전송합니다."""
        if rst == 0: # 토출 명령
            # 제공된 코드의 계산식(ice * 13, water * 12)을 적용합니다.
            apiData = [122, 17, int(ice * 13), int(water * 12), 123]
            print(f"[Icetro] API sent: dispense (ice_val={apiData[2]}, water_val={apiData[3]})")
        elif rst == 1: # 리셋 명령
            apiData = [122, 19, 0, 0, 123]
            print("[Icetro] API sent: reset")
        else:
            return

        api = bytearray(apiData)
        
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
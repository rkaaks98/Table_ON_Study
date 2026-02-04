# src/main_controller.py
import subprocess
import time
import sys
import os
import signal
import requests
import logging
import json
from logging.handlers import RotatingFileHandler

# --- Configuration ---
# [Config Load]
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'config.json')
SIMULATION_MODE = False
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
        SIMULATION_MODE = config.get('simulation_mode', False)
except Exception as e:
    print(f"Failed to load config: {e}")

print(f"[MainController] Simulation Mode: {SIMULATION_MODE}")

SERVICES = [
    {'name': 'io_service',     'path': 'src/services/io_service.py',     'port': 8400, 'check_url': '/health'},
    {'name': 'pickup_service', 'path': 'src/services/pickup_service.py', 'port': 8600, 'check_url': '/getPickupStatus/0'},
    {'name': 'device_service', 'path': 'src/services/device_service.py', 'port': 8500, 'check_url': '/coffee/status'},
    {'name': 'robot_service',  'path': 'src/services/robot_service.py',  'port': 8300, 'check_url': '/robots'},
    {'name': 'recipe_service', 'path': 'src/services/recipe_service.py', 'port': 8200, 'check_url': '/getAllRecipes'},
    {'name': 'order_service',  'path': 'src/services/order_service.py',  'port': 8100, 'check_url': '/getSystemMode'},
]

# 시뮬레이션 모드가 아닐 때만 키오스크 리더 추가
#if not SIMULATION_MODE:
#    SERVICES.append({'name': 'kiosk_reader', 'path': 'src/devices/kiosk/easypos_kiosk_reader.py', 'port': None, 'check_url': None})

# [수정] 프로젝트 루트의 logs 폴더 (src/services/../../logs -> src/../logs -> ../logs)
#__file__ = src/services/main_controller.py
#dirname1 = src/services
#dirname2 = src
#dirname3 = ProjectRoot

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- Logger Setup ---
logger = logging.getLogger("MainController")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(os.path.join(LOG_DIR, "system.log"), maxBytes=10*1024*1024, backupCount=5)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

processes = {}

def start_service(service_info):
    name = service_info['name']
    script_path = service_info['path']
    port = service_info.get('port') # port가 없을 수도 있음
    
    logger.info(f"Starting {name}...")
    
    # Determine Python Executable
    python_exe = 'python' if sys.platform == 'win32' else 'python3'
    
    # Resolve Absolute Path
    abs_script_path = os.path.abspath(script_path)
    working_dir = os.path.dirname(os.path.dirname(abs_script_path)) # src/.. -> root
    
    # [Log File Setup] - 모든 서비스 로그 기록
    log_file = None
    stdout_target = subprocess.DEVNULL

    log_file_path = os.path.join(LOG_DIR, f"{name}.log")
    try:
        log_file = open(log_file_path, 'a', encoding='utf-8')
        stdout_target = log_file
    except Exception as e:
        logger.error(f"Failed to open log file for {name}: {e}")
        return False
    
    try:
        # [Fix] 파이썬 출력 버퍼링 비활성화 (-u 옵션)
        cmd = [python_exe, '-u', abs_script_path]
        
        proc = subprocess.Popen(
            cmd,
            stdout=stdout_target,
            stderr=subprocess.STDOUT if log_file else subprocess.DEVNULL,
            text=True,
            cwd=working_dir
        )
        processes[name] = {'proc': proc, 'log_file': log_file}
        return True
    except Exception as e:
        logger.error(f"Failed to execute {name}: {e}")
        try: log_file.close()
        except: pass
        return False

def wait_for_service(service_info, timeout=15):
    if service_info.get('check_url') is None:
        # 웹 서비스가 아닌 경우, 프로세스가 살아있는지만 확인 (약간의 대기)
        time.sleep(2)
        if processes.get(service_info['name'], {}).get('proc').poll() is None:
            logger.info(f"{service_info['name']} started successfully (No Health Check).")
            return True
        else:
            logger.error(f"{service_info['name']} failed to start immediately.")
            return False

    url = f"http://localhost:{service_info['port']}{service_info['check_url']}"
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            requests.get(url, timeout=1)
            logger.info(f"{service_info['name']} is UP.")
            return True
        except:
            time.sleep(0.5)
            
    logger.error(f"{service_info['name']} failed to start (Timeout).")
    return False

def stop_all_services():
    logger.info("Stopping all services...")
    for name, info in processes.items():
        proc = info['proc']
        log_file = info['log_file']
        
        if proc.poll() is None: # Running
            logger.info(f"Terminating {name}...")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning(f"{name} did not terminate, killing...")
                proc.kill()
        
        # Close Log File
        try:
            if log_file: log_file.close()
        except: pass
        
    logger.info("All services stopped.")

def signal_handler(sig, frame):
    logger.info("Shutdown signal received.")
    stop_all_services()
    sys.exit(0)

def monitor_services():
    """Check if processes are still alive"""
    for name, info in processes.items():
        proc = info['proc']
        if proc.poll() is not None:
            logger.error(f"Service {name} died unexpectedly! Exit code: {proc.returncode}")
            # No need to read stderr here, it's in the log file
            
            # Restart Logic (Optional)
            # logger.info(f"Restarting {name}...")
            # start_service(next(s for s in SERVICES if s['name'] == name))

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=== TableON-CO-OP System Startup ===")

    # 1. Start Services Sequentially
    for svc in SERVICES:
        if start_service(svc):
            if not wait_for_service(svc):
                logger.critical(f"Critical service {svc['name']} failed to start. Aborting.")
                stop_all_services()
                return
        else:
            logger.critical(f"Failed to launch process for {svc['name']}. Aborting.")
            stop_all_services()
            return
        
        # Small delay between services
        time.sleep(1)

    logger.info("All services started successfully.")
    
    # 2. Initial System Configuration (Optional)
    try:
        # Set System to AUTO Mode by default?
        # requests.get("http://localhost:8100/setSystemMode/1")
        pass
    except:
        pass

    # 3. Main Loop (Watchdog)
    try:
        while True:
            monitor_services()
            time.sleep(5)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == '__main__':
    main()


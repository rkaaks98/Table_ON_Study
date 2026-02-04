"""
Order Service - 시뮬레이션 버전 (Standalone)
============================================
- 외부 서비스(로봇, 장비, 픽업대) 통신 없이 독립 실행
- 모든 통신은 로그로 대체
- 주문 플로우 및 병렬 처리 로직 검증용
"""

import time
import threading
import json
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

from enum import Enum, auto
from typing import List, Dict, Optional
from queue import Queue, Empty

import logging
from logging.handlers import TimedRotatingFileHandler

# --- Logger Setup ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logger = logging.getLogger("OrderServiceSim")
logger.setLevel(logging.DEBUG)

log_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "order_service_sim.log"),
    when="midnight",
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
RECIPE_PATH = os.path.join(CONFIG_DIR, 'recipe.json')

# 시뮬레이션 타이밍 설정
SIM_ROBOT_MOVE_TIME = 2.0   # 로봇 이동 시간 (초)
SIM_DEVICE_TIME = 1.0       # 장비 동작 시간 (초)
SIM_OVERRIDE_TIME = 0       # 레시피 시간 오버라이드 (초) - 0이면 원본 사용 (커피 31초 등)

# ---------------------------------------------------------
# Register & Command Codes (로그용)
# ---------------------------------------------------------
REG_CMD       = 600
REG_INIT      = 700
REG_CUP_IDX   = 100
REG_PICKUP_IDX = 101
REG_CUP_RES    = 102
REG_CUP_SET    = 103
REG_CUP_SENSOR = 104
REG_CUP_ON     = 105
REG_SYRUP_IDX  = 106
REG_F_PICK_IDX = REG_PICKUP_IDX

CMD_CUP_MOVE     = 110
CMD_WI_MOVE      = 111
CMD_WI_DONE      = 112
CMD_COFFEE_MOVE  = 113
CMD_COFFEE_DONE  = 114
CMD_COFFEE_PLACE = 115
CMD_COFFEE_PICK  = 116
CMD_HOT_MOVE     = 117
CMD_HOT_DONE     = 118
CMD_PICKUP_MOVE  = 119
CMD_PICKUP_PLACE = 120
CMD_SYRUP_MOVE   = 121
CMD_SYRUP_DONE   = 122
CMD_HOME         = 123

CMD_DESC = {
    CMD_CUP_MOVE:    "컵 배출",
    CMD_WI_MOVE:     "제빙기 접근",
    CMD_WI_DONE:     "제빙기 완료",
    CMD_COFFEE_MOVE: "커피머신 접근",
    CMD_COFFEE_DONE: "커피머신 완료",
    CMD_COFFEE_PLACE:"커피머신 컵 거치 (병렬)",
    CMD_COFFEE_PICK: "커피머신 컵 픽업 (병렬)",
    CMD_HOT_MOVE:    "온수기 접근",
    CMD_HOT_DONE:    "온수기 완료",
    CMD_PICKUP_MOVE: "픽업대 접근",
    CMD_PICKUP_PLACE:"픽업대 서빙",
    CMD_SYRUP_MOVE:  "시럽 접근",
    CMD_SYRUP_DONE:  "시럽 완료",
    CMD_HOME:        "홈 복귀",
}

MODE_MANUAL = 0
MODE_AUTO   = 1

ORDER_WAITING    = "WAITING"
ORDER_PROCESSING = "PROCESSING"
ORDER_COMPLETED  = "COMPLETED"
ORDER_CANCELLED  = "CANCELLED"

# ---------------------------------------------------------
# Simulated Interfaces (로그만 출력)
# ---------------------------------------------------------

class SimRobotInterface:
    """시뮬레이션용 로봇 인터페이스 - 실제 통신 없음"""
    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.registers = {}  # 가상 레지스터
        
    def write_register(self, addr: int, value: int) -> bool:
        self.registers[addr] = value
        logger.debug(f"[{self.robot_id}] WriteReg({addr}) = {value}")
        return True
        
    def read_register(self, addr: int) -> int:
        val = self.registers.get(addr, 0)
        logger.debug(f"[{self.robot_id}] ReadReg({addr}) = {val}")
        return val
        
    def send_command(self, cmd_code: int) -> bool:
        cmd_name = CMD_DESC.get(cmd_code, f"CMD_{cmd_code}")
        logger.info(f"[{self.robot_id}] 명령 전송: {cmd_code} ({cmd_name})")
        return True
        
    def wait_init(self, target_val: int, timeout=600.0) -> bool:
        """시뮬레이션: 짧은 딜레이 후 바로 완료"""
        cmd_code = target_val - 500
        cmd_name = CMD_DESC.get(cmd_code, f"CMD_{cmd_code}")
        logger.info(f"[{self.robot_id}] 로봇 동작 중: {cmd_name}...")
        time.sleep(SIM_ROBOT_MOVE_TIME)
        logger.info(f"[{self.robot_id}] 로봇 동작 완료: {target_val}")
        return True


class SimDeviceInterface:
    """시뮬레이션용 장비 인터페이스 - 실제 통신 없음"""
    
    def make_coffee(self, product_id, duration):
        logger.info(f"☕ [커피머신] 추출 시작 - 제품ID: {product_id}")
        time.sleep(SIM_DEVICE_TIME)
        logger.info(f"☕ [커피머신] 추출 완료")
        return True
        
    def dispense_ice_water(self, ice_time, water_time):
        logger.info(f"🧊 [제빙기] 얼음: {ice_time}초, 물: {water_time}초")
        time.sleep(SIM_DEVICE_TIME)
        logger.info(f"🧊 [제빙기] 완료")
        return True
        
    def dispense_syrup(self, code, duration):
        logger.info(f"🍯 [시럽] 코드: {code}, 시간: {duration}초")
        time.sleep(SIM_DEVICE_TIME)
        logger.info(f"🍯 [시럽] 완료")
        return True
        
    def dispense_hot_water(self, duration):
        logger.info(f"♨️ [온수기] 시간: {duration}초")
        time.sleep(SIM_DEVICE_TIME)
        logger.info(f"♨️ [온수기] 완료")
        return True
        
    def dispense_sparkling(self, duration):
        logger.info(f"🫧 [탄산수] 시간: {duration}초")
        time.sleep(SIM_DEVICE_TIME)
        logger.info(f"🫧 [탄산수] 완료")
        return True
        
    def execute_rinse(self):
        logger.info(f"🚿 [커피머신] 헹굼 실행")
        return True
        
    def stop_all_devices(self):
        logger.info(f"🛑 [장비] 전체 정지")


# ---------------------------------------------------------
# Task & Planning
# ---------------------------------------------------------

class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


class Task:
    def __init__(self, task_id: str, cmd_code: int, params: Dict[int, int] = None, 
                 dependencies: List[str] = None, order_uuid: str = None, skippable: bool = False):
        self.task_id = task_id
        self.cmd_code = cmd_code
        self.params = params or {}
        self.dependencies = dependencies or []
        self.status = TaskStatus.PENDING
        self.order_uuid = order_uuid
        self.skippable = skippable
        self.menu_name = ""
        self.order_no = 0
        self.chained_next_task_id = None
        self.pre_device_action = None 
        self.post_device_action = None
        self.notify_pickup = None
        self.assigned_slot = 0
        self.parallel_check_point = False
        self.is_coffee_wait = False


class TaskPlanner:
    def __init__(self):
        self.task_counter = 0
        self.recipes = {}
        self.load_recipes()

    def load_recipes(self):
        try:
            with open(RECIPE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.recipes = {item['menu_code']: item for item in data}
                else:
                    self.recipes = data
            logger.info(f"📋 [Planner] {len(self.recipes)}개 레시피 로드 완료")
            
            # 시뮬레이션: SIM_OVERRIDE_TIME > 0이면 해당 값으로 오버라이드, 아니면 원본 유지
            if SIM_OVERRIDE_TIME > 0:
                logger.info(f"📋 [Planner] 시뮬레이션 모드: 레시피 시간을 {SIM_OVERRIDE_TIME}초로 오버라이드")
                for code, r in self.recipes.items():
                    r['water_ext_time'] = SIM_OVERRIDE_TIME if r.get('water_ext_time', 0) > 0 else 0
                    r['ice_ext_time'] = SIM_OVERRIDE_TIME if r.get('ice_ext_time', 0) > 0 else 0
                    r['hotwater_ext_time'] = SIM_OVERRIDE_TIME if r.get('hotwater_ext_time', 0) > 0 else 0
                    r['coffee_ext_time'] = SIM_OVERRIDE_TIME if r.get('coffee_ext_time', 0) > 0 else 0
                    r['sparkling_ext_time'] = SIM_OVERRIDE_TIME if r.get('sparkling_ext_time', 0) > 0 else 0
                    if 'syrups' in r:
                        for s in r['syrups']:
                            if isinstance(s, dict) and 'time' in s:
                                s['time'] = SIM_OVERRIDE_TIME
            else:
                logger.info(f"📋 [Planner] 시뮬레이션 모드: 레시피 원본 시간 사용")
                            
        except Exception as e:
            logger.error(f"[Planner] 레시피 로드 실패: {e}")

    def _new_id(self):
        self.task_counter += 1
        return f"T{self.task_counter}"

    def get_recipe(self, menu_code: int) -> Optional[Dict]:
        return self.recipes.get(menu_code)

    def is_coffee_menu(self, menu_code: int) -> bool:
        recipe = self.get_recipe(menu_code)
        if not recipe:
            return False
        return recipe.get('coffee_ext_time', 0) > 0

    def plan_order(self, order: Dict, order_uuid: str) -> List[Task]:
        logger.info(f"📝 [Planner] 주문 플래닝: #{order['order_no']} {order.get('menu_name', '')} ({order['menu_code']})")
        
        tasks = []
        menu_code = order.get('menu_code')
        order_type = order.get('order_type', 'DINEIN')
        recipe = self.get_recipe(menu_code)
        
        if not recipe:
            logger.error(f"[Planner] 레시피 없음: {menu_code}")
            return []
        
        if system_mode == MODE_MANUAL:
            logger.warning("[Planner] 수동 모드 - 플래닝 스킵")
            return []
            
        tasks = self._plan_order_unified(recipe, order_type, order, order_uuid)

        for t in tasks:
            t.menu_name = order.get('menu_name', '')
            t.order_no = order.get('order_no', 0)

        # 태스크 목록 출력
        task_list = " → ".join([f"{t.task_id}({CMD_DESC.get(t.cmd_code, t.cmd_code)})" for t in tasks])
        logger.info(f"📋 [Planner] 태스크: {task_list}")
        
        return tasks

    def _plan_serve_sequence(self, tasks, order_type, last_task_id, order, recipe, order_uuid):
        t_move = Task(self._new_id(), CMD_PICKUP_MOVE, {}, dependencies=[last_task_id], order_uuid=order_uuid)
        tasks.append(t_move)
        
        t_serve = Task(self._new_id(), CMD_PICKUP_PLACE, {}, dependencies=[t_move.task_id], order_uuid=order_uuid)
        t_move.chained_next_task_id = t_serve.task_id
        t_serve.notify_pickup = {'zone': 1, 'order_no': order.get('order_no', 0), 'menu_code': recipe.get('menu_code', 0)}
        tasks.append(t_serve)
        
        t_home = Task(self._new_id(), CMD_HOME, {}, dependencies=[t_serve.task_id], order_uuid=order_uuid, skippable=True)
        tasks.append(t_home)
        
        return t_home.task_id

    def _plan_syrup_sequence(self, tasks, recipe, prev_task_id, order_uuid=None):
        syrups = recipe.get('syrups', [])
        if not syrups:
            return prev_task_id
        
        last_task_id = prev_task_id
        
        for syrup in syrups:
            syrup_id = syrup.get('id', 1)
            syrup_time = syrup.get('time', 3)
            
            t_move = Task(self._new_id(), CMD_SYRUP_MOVE, {REG_SYRUP_IDX: syrup_id}, 
                         dependencies=[last_task_id], order_uuid=order_uuid)
            t_move.post_device_action = {'type': 'syrup', 'params': {'code': syrup_id, 'time': syrup_time}}
            tasks.append(t_move)
            
            t_done = Task(self._new_id(), CMD_SYRUP_DONE, {}, 
                         dependencies=[t_move.task_id], order_uuid=order_uuid)
            t_move.chained_next_task_id = t_done.task_id
            tasks.append(t_done)
            last_task_id = t_done.task_id
        
        return last_task_id

    def _plan_order_unified(self, recipe, order_type, order, order_uuid):
        tasks = []
        
        # 1. 컵 배출
        t_cup = Task(self._new_id(), CMD_CUP_MOVE, {REG_CUP_IDX: recipe['cup_num']}, order_uuid=order_uuid)
        tasks.append(t_cup)
        last_task_id = t_cup.task_id
        
        # 2. 제빙기
        ice_time = recipe.get('ice_ext_time', 0)
        water_time = recipe.get('water_ext_time', 0)
        sparkling_time = recipe.get('sparkling_ext_time', 0)
        
        if ice_time > 0 or water_time > 0 or sparkling_time > 0:
            t_wi_move = Task(self._new_id(), CMD_WI_MOVE, {}, dependencies=[last_task_id], order_uuid=order_uuid)
            t_wi_move.post_device_action = {
                'type': 'ice_water_sparkling',
                'params': {'ice': ice_time, 'water': water_time, 'sparkling': sparkling_time}
            }
            tasks.append(t_wi_move)
            
            t_wi_done = Task(self._new_id(), CMD_WI_DONE, {}, dependencies=[t_wi_move.task_id], order_uuid=order_uuid)
            t_wi_move.chained_next_task_id = t_wi_done.task_id
            tasks.append(t_wi_done)
            last_task_id = t_wi_done.task_id
        
        # 3. 온수기
        hot_time = recipe.get('hotwater_ext_time', 0)
        if hot_time > 0:
            t_hot_move = Task(self._new_id(), CMD_HOT_MOVE, {}, dependencies=[last_task_id], order_uuid=order_uuid)
            t_hot_move.post_device_action = {'type': 'hot_water', 'params': {'time': hot_time}}
            tasks.append(t_hot_move)
            
            t_hot_done = Task(self._new_id(), CMD_HOT_DONE, {}, dependencies=[t_hot_move.task_id], order_uuid=order_uuid)
            t_hot_move.chained_next_task_id = t_hot_done.task_id
            tasks.append(t_hot_done)
            last_task_id = t_hot_done.task_id
        
        # 4. 커피머신 (병렬 처리 체크 포인트)
        coffee_time = recipe.get('coffee_ext_time', 0)
        if coffee_time > 0:
            t_coffee_move = Task(self._new_id(), CMD_COFFEE_MOVE, {}, dependencies=[last_task_id], order_uuid=order_uuid)
            t_coffee_move.parallel_check_point = True
            t_coffee_move.pre_device_action = {
                'type': 'coffee',
                'params': {'id': recipe.get('coffee_product_id', 1), 'time': 0.5}
            }
            tasks.append(t_coffee_move)
            
            t_coffee_done = Task(self._new_id(), CMD_COFFEE_DONE, {}, dependencies=[t_coffee_move.task_id], order_uuid=order_uuid)
            t_coffee_done.is_coffee_wait = True
            t_coffee_done.post_device_action = {'type': 'sleep', 'params': {'time': coffee_time}}
            t_coffee_move.chained_next_task_id = t_coffee_done.task_id
            tasks.append(t_coffee_done)
            last_task_id = t_coffee_done.task_id
        
        # 5. 시럽
        last_task_id = self._plan_syrup_sequence(tasks, recipe, last_task_id, order_uuid)
        
        # 6. 서빙
        self._plan_serve_sequence(tasks, order_type, last_task_id, order, recipe, order_uuid)
        
        return tasks


# ---------------------------------------------------------
# Scheduler
# ---------------------------------------------------------

class TaskScheduler:
    def __init__(self):
        self.tasks: List[Task] = []
        self.robot = SimRobotInterface('robot_1')
        self.devices = SimDeviceInterface()
        
        self.pickup_slot_counter = 0
        self.running = False
        self.thread = None
        self.robot_busy = False
        self.robot_chained_task = None
        
        # 병렬 처리
        self.parallel_mode = False
        self.parallel_completed = False
        self.paused_coffee_task = None
        self.paused_coffee_uuid = None
        self.paused_coffee_order = None
        
        self.fail_safe_callback = None
        self.skip_callback = None
        self.status_callback = None
        self.order_manager = None
        self.planner = None

    def set_fail_safe_callback(self, callback):
        self.fail_safe_callback = callback

    def set_skip_condition_callback(self, callback):
        self.skip_callback = callback

    def set_status_callback(self, callback):
        self.status_callback = callback

    def set_order_manager(self, order_manager):
        self.order_manager = order_manager

    def set_planner(self, planner):
        self.planner = planner

    def get_empty_pickup_slot(self, zone_id: int) -> int:
        """시뮬레이션: 순환하며 슬롯 할당"""
        self.pickup_slot_counter = (self.pickup_slot_counter % 3) + 1
        return self.pickup_slot_counter

    def cancel_tasks(self, order_uuid: str):
        original_count = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.order_uuid != order_uuid]
        removed_count = original_count - len(self.tasks)
        logger.info(f"🗑️ [Scheduler] {removed_count}개 태스크 취소됨 (UUID: {order_uuid})")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("▶️ [Scheduler] 시작됨")

    def stop_all(self):
        logger.warning("🛑 [Scheduler] 비상 정지!")
        self.tasks.clear()
        self.robot_busy = False
        self.robot_chained_task = None
        self.parallel_mode = False

    def add_tasks(self, new_tasks: List[Task]):
        self.tasks.extend(new_tasks)
        logger.info(f"➕ [Scheduler] {len(new_tasks)}개 태스크 추가됨. 총: {len(self.tasks)}")

    def _check_parallel_opportunity(self, current_order_uuid) -> Optional[str]:
        if not self.order_manager or not self.planner:
            return None
            
        waiting_orders = [
            o for o in self.order_manager.active_orders.values()
            if o['status'] == ORDER_WAITING and o['uuid'] != current_order_uuid
        ]
        
        # ⭐ 주문 시간 순으로 정렬 (선입선출)
        waiting_orders.sort(key=lambda x: x.get('created_at', 0))
        
        for order in waiting_orders:
            menu_code = order.get('menu_code')
            if not self.planner.is_coffee_menu(menu_code):
                # ⭐ 병렬 처리 대상 선택 → 상태 변경 및 기존 태스크 취소
                order['status'] = ORDER_PROCESSING
                self.cancel_tasks(order['uuid'])  # OrderManager가 생성한 태스크 취소
                return order['uuid']
        return None

    def _loop(self):
        while self.running:
            pending_tasks = [t for t in self.tasks if t.status == TaskStatus.PENDING]
            
            for task in pending_tasks:
                if self.robot_chained_task and task.task_id != self.robot_chained_task:
                    continue
                
                if self.robot_busy:
                    continue
                if not self._check_dependencies(task):
                    continue 
                
                threading.Thread(target=self._execute_task_wrapper, args=(task,)).start()
                break 

            time.sleep(0.05)

    def _check_dependencies(self, task: Task) -> bool:
        for dep_id in task.dependencies:
            dep_task = next((t for t in self.tasks if t.task_id == dep_id), None)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def _execute_task_wrapper(self, task: Task):
        self.robot_busy = True
        
        try:
            task.status = TaskStatus.RUNNING
            
            if task.order_uuid and self.status_callback:
                self.status_callback(task.order_uuid, ORDER_PROCESSING)

            should_skip = False
            if task.skippable:
                pending_count = len([t for t in self.tasks if t.status == TaskStatus.PENDING])
                if pending_count > 0:
                    should_skip = True

            if should_skip:
                logger.info(f"⏭️ [Scheduler] 태스크 스킵: {task.task_id}")
                self.robot_chained_task = None
            else:
                self._execute_task(task)
                
                if self.parallel_completed:
                    self.robot_chained_task = None
                    self.parallel_completed = False
                elif task.chained_next_task_id:
                    self.robot_chained_task = task.chained_next_task_id
                else:
                    self.robot_chained_task = None
            
            task.status = TaskStatus.COMPLETED
            
            if task.order_uuid and self.status_callback:
                remaining = [t for t in self.tasks if t.order_uuid == task.order_uuid and t.status != TaskStatus.COMPLETED]
                if not remaining:
                    self.status_callback(task.order_uuid, ORDER_COMPLETED)
            
        except Exception as e:
            logger.error(f"[Scheduler] 태스크 실패 {task.task_id}: {e}")
            task.status = TaskStatus.FAILED
            self.robot_chained_task = None
            
        finally:
            self.robot_busy = False

    def _execute_task(self, task: Task):
        robot = self.robot
        
        actual_cmd = task.cmd_code
        parallel_uuid = None
        
        # 병렬 처리 체크
        if task.parallel_check_point and self.order_manager and self.planner:
            parallel_uuid = self._check_parallel_opportunity(task.order_uuid)
            
            if parallel_uuid:
                actual_cmd = CMD_COFFEE_PLACE
                logger.info(f"🔀 [Parallel] 비커피 주문 발견! 병렬 처리 시작")
                logger.info(f"🔀 [Parallel] 명령 변경: {task.cmd_code} → {actual_cmd} (Place)")
                
                self.paused_coffee_task = task
                self.paused_coffee_uuid = task.order_uuid
                coffee_order = self.order_manager.active_orders.get(task.order_uuid)
                if coffee_order:
                    self.paused_coffee_order = coffee_order.copy()
        
        # Pre Action
        if task.pre_device_action:
            self._execute_device_action(task.pre_device_action)

        # Pickup Slot
        if task.cmd_code == CMD_PICKUP_PLACE:
            slot = self.get_empty_pickup_slot(1)
            task.assigned_slot = slot
            task.params[REG_F_PICK_IDX] = slot
            logger.info(f"📍 [Scheduler] 픽업 슬롯 할당: {slot}")

        # 로봇 명령 실행
        cmd_name = CMD_DESC.get(actual_cmd, f"CMD_{actual_cmd}")
        logger.info(f"═══════════════════════════════════════════")
        logger.info(f"🎯 [{task.task_id}] {cmd_name} | 주문#{task.order_no} {task.menu_name}")
        
        for addr, val in task.params.items():
            robot.write_register(addr, val)
            
        robot.send_command(actual_cmd)
        
        expected_init = actual_cmd + 500
        robot.wait_init(expected_init)

        # 컵 배출 프로세스 (시뮬레이션)
        if task.cmd_code == CMD_CUP_MOVE:
            cup_idx = task.params.get(REG_CUP_IDX, 1)
            cup_type = "HOT" if cup_idx == 1 else "ICE"
            coil_addr = 3203 if cup_idx == 1 else 3204
            
            logger.info(f"   🥤 [Cup] CUP_ON(105) 대기...")
            time.sleep(0.5)  # 시뮬레이션 대기
            logger.info(f"   🥤 [Cup] CUP_ON 수신, 초기화")
            logger.info(f"   🥤 [Cup] 컵 추출 신호 ({cup_type}) - Unit:5, Addr:{coil_addr}")
            time.sleep(1.0)  # 컵 추출 시간
            logger.info(f"   🥤 [Cup] CUP_RES=1 (성공)")
            
            # cup_idx 업데이트 (HOT:1→3, ICE:2→4)
            new_cup_idx = 3 if cup_idx == 1 else 4
            robot.write_register(REG_CUP_IDX, new_cup_idx)
            logger.info(f"   🥤 [Cup] CUP_IDX 업데이트: {cup_idx} → {new_cup_idx}")

        # 병렬 처리
        if parallel_uuid and actual_cmd == CMD_COFFEE_PLACE:
            self._process_parallel_order(task, parallel_uuid)
            return 
            
        # Post Action
        if task.post_device_action:
            self._execute_device_action(task.post_device_action)
            
        # Notify Pickup
        if task.notify_pickup:
            logger.info(f"🔔 [Pickup] 서빙 완료 알림 - Zone:{task.notify_pickup['zone']} Slot:{task.assigned_slot} 주문#{task.notify_pickup['order_no']}")

    def _process_parallel_order(self, coffee_task: Task, parallel_uuid: str):
        """병렬 처리 로직"""
        robot = self.robot
        self.parallel_mode = True
        
        PARALLEL_THRESHOLD = 20.0  # 남은 시간이 이 값 이상일 때만 추가 병렬 처리
        
        logger.info(f"")
        logger.info(f"╔═══════════════════════════════════════════╗")
        logger.info(f"║       🔀 병렬 처리 모드 시작              ║")
        logger.info(f"╚═══════════════════════════════════════════╝")
        logger.info(f"   대기중인 커피: {self.paused_coffee_order.get('menu_name') if self.paused_coffee_order else 'N/A'}")
        
        # 커피 추출 시간
        recipe = None
        if self.paused_coffee_order and self.planner:
            recipe = self.planner.get_recipe(self.paused_coffee_order.get('menu_code'))
        
        coffee_duration = recipe.get('coffee_ext_time', 30) if recipe else 30
        coffee_start_time = time.time()
        
        logger.info(f"   ☕ 커피 추출 시작 (예상 시간: {coffee_duration}초)")
        
        # 비커피 음료 처리
        current_parallel_uuid = parallel_uuid
        parallel_count = 0
        
        while current_parallel_uuid and self.running:
            parallel_count += 1
            parallel_order = self.order_manager.active_orders.get(current_parallel_uuid)
            
            if not parallel_order:
                break
            
            # ⭐ 병렬 주문 상태를 즉시 PROCESSING으로 변경 (중복 처리 방지)
            parallel_order['status'] = ORDER_PROCESSING
                
            logger.info(f"")
            logger.info(f"   ────────────────────────────────────────")
            logger.info(f"   🥤 병렬 주문 #{parallel_count}: {parallel_order.get('menu_name')}")
            logger.info(f"   ────────────────────────────────────────")
        
            parallel_tasks = self.planner.plan_order(parallel_order, current_parallel_uuid)
        
            for t in parallel_tasks:
                t.menu_name = parallel_order.get('menu_name', '')
                t.order_no = parallel_order.get('order_no', 0)
            
            for pt in parallel_tasks:
                if not self.running:
                    break
                    
                pt.status = TaskStatus.RUNNING
                
                if self.status_callback:
                    self.status_callback(current_parallel_uuid, ORDER_PROCESSING)
                
                try:
                    self._execute_task(pt)
                    pt.status = TaskStatus.COMPLETED
                except Exception as e:
                    logger.error(f"   [ERROR] 병렬 태스크 실패: {e}")
                    pt.status = TaskStatus.FAILED
                    break
            
            if self.status_callback:
                self.status_callback(current_parallel_uuid, ORDER_COMPLETED)
            
            logger.info(f"   [OK] 병렬 주문 #{parallel_count} 완료!")
            
            # 남은 시간 체크
            elapsed = time.time() - coffee_start_time
            remaining = coffee_duration - elapsed
            
            logger.info(f"   ⏱️ 커피 남은 시간: {remaining:.1f}초")
            
            if remaining >= PARALLEL_THRESHOLD:
                next_parallel = self._check_parallel_opportunity(self.paused_coffee_uuid)
                if next_parallel:
                    logger.info(f"   🔍 추가 비커피 주문 발견!")
                    current_parallel_uuid = next_parallel
                    continue
                else:
                    current_parallel_uuid = None
            else:
                current_parallel_uuid = None
        
        logger.info(f"")
        logger.info(f"   📊 총 {parallel_count}개 병렬 주문 처리 완료")
        
        # 커피 추출 대기
        elapsed = time.time() - coffee_start_time
        remaining = coffee_duration - elapsed
        
        if remaining > 0:
            logger.info(f"   ⏳ 커피 추출 대기 중... ({remaining:.1f}초)")
            time.sleep(remaining)
        
        logger.info(f"   ☕ 커피 추출 완료!")
        
        # 커피 픽업
        logger.info(f"")
        logger.info(f"   [Robot] 커피머신에서 컵 픽업 (CMD: 116)")
        robot.send_command(CMD_COFFEE_PICK)
        robot.wait_init(CMD_COFFEE_PICK + 500)
        
        # COFFEE_DONE 태스크 스킵
        if coffee_task.chained_next_task_id:
            coffee_done_task = next((t for t in self.tasks if t.task_id == coffee_task.chained_next_task_id), None)
            if coffee_done_task:
                logger.info(f"   ⏭️ COFFEE_DONE 태스크 스킵: {coffee_done_task.task_id}")
                coffee_done_task.status = TaskStatus.COMPLETED
        
        logger.info(f"")
        logger.info(f"╔═══════════════════════════════════════════╗")
        logger.info(f"║       [OK] 병렬 처리 완료                  ║")
        logger.info(f"╚═══════════════════════════════════════════╝")
        logger.info(f"   커피 주문 재개: {self.paused_coffee_order.get('menu_name') if self.paused_coffee_order else 'N/A'}")
        logger.info(f"")
        
        self.parallel_completed = True
        self.parallel_mode = False
        self.paused_coffee_task = None
        self.paused_coffee_uuid = None
        self.paused_coffee_order = None

    def _execute_device_action(self, action):
        act_type = action.get('type')
        p = action.get('params', {})
        
        if act_type == 'coffee':
            self.devices.make_coffee(p.get('id'), p.get('time'))
        elif act_type == 'ice_water':
            self.devices.dispense_ice_water(p.get('ice'), p.get('water'))
        elif act_type == 'ice_water_sparkling':
            self.devices.dispense_ice_water(p.get('ice'), p.get('water'))
            if p.get('sparkling', 0) > 0:
                self.devices.dispense_sparkling(p.get('sparkling'))
        elif act_type == 'hot_water':
            self.devices.dispense_hot_water(p.get('time'))
        elif act_type == 'syrup':
            self.devices.dispense_syrup(p.get('code'), p.get('time'))
        elif act_type == 'sparkling':
            self.devices.dispense_sparkling(p.get('time'))
        elif act_type == 'sleep':
            duration = float(p.get('time', 0))
            logger.info(f"💤 [대기] {duration}초...")
            time.sleep(duration)  # 레시피 시간 그대로 사용


# ---------------------------------------------------------
# Order Management
# ---------------------------------------------------------

class OrderManager:
    def __init__(self, planner: TaskPlanner, scheduler: TaskScheduler):
        self.order_queue = Queue()
        self.active_orders = {} 
        self.planner = planner
        self.scheduler = scheduler
        self.scheduler.set_status_callback(self.update_order_status)
        self.scheduler.set_skip_condition_callback(lambda: not self.order_queue.empty())
        self.scheduler.set_order_manager(self)
        self.scheduler.set_planner(planner)
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("📦 [OrderManager] 시작됨")

    def add_order(self, order):
        order_uuid = f"{int(time.time() * 1000)}"
        order['uuid'] = order_uuid
        order['status'] = ORDER_WAITING
        order['created_at'] = time.time()
        
        self.active_orders[order_uuid] = order
        self.order_queue.put(order_uuid)
        
        logger.info(f"")
        logger.info(f"🆕 ═══════════════════════════════════════════")
        logger.info(f"   새 주문 접수!")
        logger.info(f"   주문번호: #{order['order_no']}")
        logger.info(f"   메뉴: {order.get('menu_name', '')} (코드: {order['menu_code']})")
        logger.info(f"   UUID: {order_uuid}")
        logger.info(f"═══════════════════════════════════════════════")
        
        return order_uuid

    def update_order_status(self, order_uuid, status):
        if order_uuid in self.active_orders:
            old_status = self.active_orders[order_uuid]['status']
            self.active_orders[order_uuid]['status'] = status
            
            if status == ORDER_COMPLETED:
                self.active_orders[order_uuid]['completed_at'] = time.time()
                elapsed = self.active_orders[order_uuid]['completed_at'] - self.active_orders[order_uuid]['created_at']
                logger.info(f"")
                logger.info(f"[OK] ═══════════════════════════════════════════")
                logger.info(f"   주문 완료!")
                logger.info(f"   주문번호: #{self.active_orders[order_uuid]['order_no']}")
                logger.info(f"   메뉴: {self.active_orders[order_uuid].get('menu_name', '')}")
                logger.info(f"   소요시간: {elapsed:.1f}초")
                logger.info(f"═══════════════════════════════════════════════")

    def cancel_order(self, order_uuid):
        if order_uuid in self.active_orders:
            self.active_orders[order_uuid]['status'] = ORDER_CANCELLED
            self.scheduler.cancel_tasks(order_uuid)
            logger.info(f"[CANCELLED] 주문 취소됨: {order_uuid}")
            return True
        return False

    def _monitor_loop(self):
        while self.running:
            # ⭐ 자동 모드가 아니면 대기 (큐에서 꺼내지 않음)
            if system_mode != MODE_AUTO:
                time.sleep(0.5)
                continue
                
            try:
                order_uuid = self.order_queue.get(timeout=1.0)
            
                if order_uuid not in self.active_orders:
                    continue
            
                order = self.active_orders[order_uuid]
                
                if order['status'] != ORDER_WAITING:
                    continue
            
                tasks = self.planner.plan_order(order, order_uuid)
                
                if tasks:
                    self.scheduler.add_tasks(tasks)
                    
            except Empty:
                pass
            except Exception as e:
                logger.error(f"[OrderManager] 오류: {e}")
                time.sleep(1.0)


# ---------------------------------------------------------
# Global State & API
# ---------------------------------------------------------
system_mode = MODE_MANUAL
planner = None
scheduler = None
order_manager = None

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'OK', 'mode': system_mode, 'simulation': True})

@app.route('/getSystemMode', methods=['GET'])
def get_system_mode():
    return jsonify({'mode': system_mode})

@app.route('/setSystemMode/<int:mode>', methods=['GET', 'POST'])
def set_system_mode(mode):
    global system_mode
    old_mode = system_mode
    system_mode = mode
    
    if mode == MODE_MANUAL and old_mode == MODE_AUTO:
        scheduler.stop_all()
    
    mode_name = "자동" if mode == MODE_AUTO else "수동"
    logger.info(f"⚙️ 시스템 모드 변경: {old_mode} → {mode} ({mode_name})")
    return jsonify({'mode': system_mode})

@app.route('/addOrder/<int:order_no>/<int:menu_code>', methods=['GET'])
def add_order_url(order_no, menu_code):
    recipe = planner.get_recipe(menu_code) if planner else None
    menu_name = recipe.get('menu_name', f'Menu {menu_code}') if recipe else f'Menu {menu_code}'

    order = {
        'order_no': order_no,
        'menu_code': menu_code,
        'menu_name': menu_name
    }
    
    order_uuid = order_manager.add_order(order)
    return jsonify({'uuid': order_uuid, 'status': ORDER_WAITING})

@app.route('/addOrder', methods=['POST'])
def add_order_json():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    
    if 'menu_name' not in data and 'menu_code' in data:
        recipe = planner.get_recipe(data['menu_code']) if planner else None
        data['menu_name'] = recipe.get('menu_name', f"Menu {data['menu_code']}") if recipe else f"Menu {data['menu_code']}"
    
    order_uuid = order_manager.add_order(data)
    return jsonify({'uuid': order_uuid, 'status': ORDER_WAITING})

@app.route('/getOrders', methods=['GET'])
def get_orders():
    return jsonify(list(order_manager.active_orders.values()))

@app.route('/getActiveOrders', methods=['GET'])
def get_active_orders():
    active = [o for o in order_manager.active_orders.values() 
              if o['status'] in [ORDER_WAITING, ORDER_PROCESSING]]
    return jsonify(active)

@app.route('/cancelOrder/<string:order_uuid>', methods=['GET', 'POST'])
def cancel_order(order_uuid):
    success = order_manager.cancel_order(order_uuid)
    return jsonify({'success': success})

@app.route('/getSchedulerStatus', methods=['GET'])
def get_scheduler_status():
    pending = len([t for t in scheduler.tasks if t.status == TaskStatus.PENDING])
    running = len([t for t in scheduler.tasks if t.status == TaskStatus.RUNNING])
    return jsonify({
        'pending_tasks': pending,
        'running_tasks': running,
        'robot_busy': scheduler.robot_busy,
        'parallel_mode': scheduler.parallel_mode
    })

@app.route('/emergencyStop', methods=['GET', 'POST'])
def emergency_stop():
    global system_mode
    system_mode = MODE_MANUAL
    scheduler.stop_all()
    logger.warning("🛑 비상 정지 실행됨")
    return jsonify({'status': 'stopped'})

@app.route('/getAllRecipes', methods=['GET'])
def get_all_recipes():
    return jsonify(list(planner.recipes.values()))

@app.route('/getRecipe/<int:menu_code>', methods=['GET'])
def get_recipe(menu_code):
    recipe = planner.get_recipe(menu_code)
    if recipe:
        return jsonify(recipe)
    return jsonify({'error': 'Not found'}), 404


def initialize():
    global planner, scheduler, order_manager
    
    planner = TaskPlanner()
    scheduler = TaskScheduler()
    scheduler.start()
    
    order_manager = OrderManager(planner, scheduler)
    
    logger.info("")
    logger.info("╔═══════════════════════════════════════════════════╗")
    logger.info("║     Order Service (Simulation) Started           ║")
    logger.info("║     - 외부 서비스 연결 없음 (독립 실행)            ║")
    logger.info("║     - 모든 통신은 로그로 대체                      ║")
    logger.info("╚═══════════════════════════════════════════════════╝")
    logger.info("")


if __name__ == '__main__':
    initialize()
    print("")
    print("=" * 55)
    print("  [START] 시뮬레이션 서버 시작: http://localhost:8100")
    print("=" * 55)
    print("")
    print("  사용법:")
    print("  1. 자동 모드 전환:")
    print("     curl http://localhost:8100/setSystemMode/1")
    print("")
    print("  2. 주문 추가:")
    print("     curl http://localhost:8100/addOrder/1001/2")
    print("     (주문번호: 1001, 메뉴코드: 2=아이스아메리카노)")
    print("")
    print("  3. 병렬 처리 테스트 (커피 + 비커피):")
    print("     curl http://localhost:8100/addOrder/1001/2")
    print("     curl http://localhost:8100/addOrder/1002/13")
    print("     (아이스 아메리카노 + 자몽에이드)")
    print("")
    print("=" * 55)
    
    app.run(host='0.0.0.0', port=8100, debug=False, threaded=True)


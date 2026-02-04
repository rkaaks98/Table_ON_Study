# 프로젝트 학습 진행 상황 및 가이드 (Handover Document)

## 1. 프로젝트 개요
- **목표**: 뉴로메카 인디(Indy) 로봇을 활용한 무인 카페 시스템(TableON)의 핵심 로직을 클론 코딩하며 학습.
- **현재 단계**: 단일 시퀀스 제어 성공 후, **Flask 기반의 HTTP API 주문 서버 구조**로 확장 중.
- **최종 지향점**: 백업 코드(`order_service.py`) 수준의 비동기 주문 처리 및 시스템 안정성 확보.

## 2. 지금까지의 학습 및 구현 내용 (Step 1 - 초기 구현)
### 2.1 로봇 통신 기초 (RobotController 클래스)
- **라이브러리**: `neuromeka.IndyDCP3` 사용.
- **핵심 메서드**:
    - `read_register(address)`: `get_int_variable()`을 통해 전체 변수를 가져온 후 특정 주소(`addr`)의 값을 필터링하여 반환.
    - `write_register(address, value)`: `set_int_variable(int_variables=[{'addr': address, 'value': value}])` 형식을 사용하여 로봇 레지스터에 값 기록.
    - `wait_for_init(init_code)`: 로봇의 완료 신호를 감시하고, 확인 즉시 해당 레지스터를 `0`으로 초기화하는 동기화 로직 구현.

### 2.2 시퀀스 제어 (run_robot_sequence 함수)
- **조건부 동작**: 레시피 데이터의 시간(`ext_time`)이 `0`보다 클 때만 해당 구간(물, 얼음, 커피 등)을 실행하도록 구현.
- **논리적 최적화**: 물과 얼음 동시 추출 시 `max(water_time, ice_time)`을 사용하여 효율적인 대기 시간 계산.
- **절차**: 컵 가져오기 -> 물/얼음 -> 온수 -> 커피 -> 서빙 -> 홈 복귀의 표준 흐름 정립.

### 2.3 데이터 모델링
- `config/recipe.json` 파일을 읽어와 딕셔너리 리스트 형태로 관리.
- `menu_code`를 기준으로 특정 메뉴의 레시피를 검색하는 `next(...)` 문법 활용.

## 3. Flask 서버 및 비동기 구조 확장 (Step 2 - 금일 진행 완료)
### 3.1 Flask 주문 서버 전환
- **목적**: 프로그램을 실행하고 한 번에 끝내는 것이 아니라, 상시 대기하며 외부(브라우저/키오스크) 주문을 처리함.
- **구조적 변화**:
    - `main()` 루프 대신 `app.run()`을 통한 서버 가동.
    - `@app.route('/order/<int:menu_code>')` 엔드포인트를 통해 주문 접수.

### 3.2 주문 처리 아키텍처 (Queue & Worker Pattern)
- **비동기 처리**: `threading`과 `queue`를 도입하여 주문 접수(Flask)와 로봇 동작(Worker)을 분리.
- **구조**: `Flask API` -> `Queue` -> `Robot Worker`. 로봇이 제조 중일 때도 서버가 멈추지 않음(Non-blocking).

### 3.3 안전 모니터링 (Monitor Worker)
- **기능**: 1초마다 로봇의 상태(`op_state`)를 감시.
- **비상 정지**: 로봇이 운전 중(`is_running=True`)인데 에러(`COLLISION` 등)가 감지되면 즉시 프로그램을 정지시키고 **대기 중인 모든 주문을 삭제(Reset)**함.

### 3.4 API 엔드포인트 현황
- `/set_robot_status/<int:status>`: 로봇 운전 모드 시작(1)/정지(0).
- `/order/<int:menu_code>`: 주문 접수.
- `/status`: 현재 시스템 상태(대기열 수, 현재 제조 중인 메뉴, 완료된 주문 목록) 조회.

### 3.5 디버깅 학습 (main_study.py)
- 의도적인 버그(NameError, AttributeError, Logical Error) 해결 실습 완료.
- 전역 변수(`global`) 스코프와 스레드 간 데이터 공유 이해.

## 4. 다음 에이전트를 위한 가이드라인 (Next Step)
### 4.1 상태 관리 고도화
- 현재는 메모리 상의 변수(`current_processing_order`, `completed_orders_list`)로만 관리 중.
- **DB 연동**: SQLite/MySQL을 도입하여 서버 재시작 시에도 데이터 유지 필요.

### 4.2 예외 처리 및 기능 강화
- **주문 취소**: `/cancel` 기능을 통해 잘못된 주문 취소 로직 구현.
- **로깅**: `logging` 모듈을 사용하여 파일로 로그 남기기.
- **네트워크 재연결**: 로봇 연결 끊김 시 자동 재연결 로직 추가.

## 5. 주요 참고 파일
- `main.py`: 현재 직접 수정하며 학습 중인 메인 파일 (Flask + Worker).
- `main_study.py`: 디버깅 챌린지 및 실험용 파일.
- `config/recipe.json`: 메뉴 설정 데이터.
- `TableON - backup/`: 전체 시스템의 완성본 참조 코드.

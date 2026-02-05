# 프로젝트 학습 진행 상황 및 가이드 (Handover Document)

## 1. 프로젝트 개요
- **목표**: 뉴로메카 인디(Indy) 로봇을 활용한 무인 카페 시스템(TableON)의 핵심 로직을 클론 코딩하며 학습.
- **현재 단계**: Flask 기반 비동기 서버 안정화, **범용 IO 제어 시스템(Modbus RTU)** 통합 및 **정밀 시퀀스 동기화** 완료.
- **최종 지향점**: 백업 코드(`order_service.py`) 수준의 비동기 주문 처리 및 시스템 안정성 확보.

## 2. 지금까지의 학습 및 구현 내용

### 2.1 로봇 통신 및 제어 (RobotController)
- **기본 통신**: `IndyDCP3` 활용 레지스터 읽기/쓰기.
- **동기화 로직**: `wait_for_init` 및 `wait_for_register`를 통한 로봇-서버 간 정밀 타이밍 제어.
- **응답 처리**: `wait_for_register`를 개선하여 성공(1)/실패(2) 등 다양한 응답을 수신하고 즉시 0으로 초기화(Auto Reset)하는 로직 구현.
- **안전장치**: `start_program` 시 로봇 상태(Home/Station) 확인, `move_home` 시 위험 상태(Collision 등) 체크 로직 추가.

### 2.2 범용 IO 제어 시스템 (DeviceController)
- **프로토콜**: RS-485 (Modbus RTU) 기반 제어 구조 설계.
- **데이터 모델**: Coils(출력), Discrete Inputs(입력) 개념 학습 및 적용.
- **IO Map 정의**:
    - **Card 3 (Unit 3)**: DI 6 (컵 센서)
    - **Card 5 (Unit 5)**: DO 3200(얼음), 3201(핫컵), 3202(아이스컵), 3203(탄산수)
    - **Card 6 (Unit 6)**: DO 3300~3307 (시럽 펌프 8개)
- **핵심 기능**: `write_coil`, `read_input`, `pulse_coil` (ON -> Sleep -> OFF) 구현.
- **시뮬레이션 모드**: 실제 장비 없이 로그로 동작을 확인할 수 있는 가상 모드(Virtual Mode) 구축.

### 2.3 정밀 제조 시퀀스 (run_robot_sequence)
- **컵 시퀀스 고도화**:
    1. `GET_CUP` 명령 전송
    2. `CUP_IDX` (1:Hot, 2:Ice) 트리거 전송
    3. 로봇 이동 대기 (`CUP_IN == 1`)
    4. 컵 배출 명령 (`CUP_IDX` 3 or 4) 및 실제 IO 동작
    5. 센서 확인 요청 대기 (`SENSOR_IN == 1`)
    6. 센서 값 읽기 및 결과 전송 (`SENSOR_ON` 1:성공, 2:실패)
    7. 최종 완료 대기 (`CUP_RES == 1`)
- **픽업 시스템 고도화**:
    - **PICKUP_IDX (102)** 레지스터 정의.
    - 4개의 픽업 슬롯 상태 관리 로직 구현 (`pickup_slots`).
    - 제조 완료 직전 빈 슬롯을 탐색하여 가장 낮은 번호의 IDX를 로봇에 전달하는 시퀀스 추가.
    - 사용자가 음료 수령 시 슬롯을 비워주는 API (`/pickup/complete/<idx>`) 구현.
- **실패 핸들링**: 컵 미감지 또는 로봇 에러 시 즉시 시퀀스 중단 및 안전 정지.

### 2.4 시스템 인프라 및 모니터링
- **로깅 시스템**: `logging` 모듈 및 `RotatingFileHandler` 적용. `logs/system.log`에 시간별 기록 저장.
- **안전 모니터링**: `monitor_worker` 쓰레드가 로봇 상태를 실시간 감시하여 에러 발생 시 즉시 정지 및 큐 초기화.
- **아키텍처 이해**: 단일 서버(Monolithic) 내 직접 함수 호출 방식과 분산 서버(MSA) 간 HTTP API 통신의 차이점 학습.

## 3. 주요 팁 및 주의사항
- **HTTP GET의 위험성**: 브라우저(Chrome)의 프리페치 기능으로 인해 주소 입력만으로 엔드포인트가 실행될 수 있음. 실전에서는 `POST` 메서드 사용 권장.
- **레지스터 초기화**: 로봇과 데이터를 주고받은 후에는 반드시 레지스터를 `0`으로 초기화하여 다음 신호와 꼬이지 않게 관리해야 함.

## 4. 다음 에이전트를 위한 가이드라인 (Next Step)
- **상태 관리**: 현재 메모리 변수 기반의 상태를 DB(SQLite 등)로 전환하여 영구 저장.
- **파일 분리**: 500줄이 넘은 `main.py`를 `controllers`, `workers`, `routes` 등으로 모듈화.
- **병렬 처리**: 커피 추출 중 로봇이 다른 작업을 수행하는 스케줄링 로직 도전.

## 5. 주요 참고 파일
- `main.py`: 핵심 로직이 통합된 메인 서버 파일.
- `MODBUS_GUIDE.md`: Modbus 데이터 모델 정리 문서.
- `config/recipe.json`: 메뉴별 제조 레시피.
- `TableON - backup/`: MSA 구조의 원본 참조 코드.

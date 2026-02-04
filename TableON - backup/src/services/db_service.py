import os
import json
import pymysql
from flask import Flask, request, jsonify
from flask_cors import CORS

# --------------------------------------------------------------------------- #
# 로거 설정
# --------------------------------------------------------------------------- #
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --------------------------------------------------------------------------- #
# Flask 앱 초기화 및 설정
# --------------------------------------------------------------------------- #
app = Flask(__name__)
CORS(app)

# --------------------------------------------------------------------------- #
# 설정 파일 로드
# --------------------------------------------------------------------------- #
def load_config():
    """설정 파일(config.json)을 로드합니다."""
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Cannot find config file at {config_path}")
        return None
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON in config file at {config_path}")
        return None

config = load_config()
if not config:
    exit()

DB_CONFIG = config.get('database', {})
SYSTEM_CONFIG = config.get('system', {})
INSTALLATION_ID = SYSTEM_CONFIG.get('installation_id')

# --------------------------------------------------------------------------- #
# 데이터베이스 연결
# --------------------------------------------------------------------------- #
def get_db_connection():
    """데이터베이스 커넥션을 생성하고 반환합니다."""
    try:
        connection = pymysql.connect(
            host=DB_CONFIG.get('host'),
            user=DB_CONFIG.get('user'),
            password=DB_CONFIG.get('password'),
            database=DB_CONFIG.get('dbname'),
            port=DB_CONFIG.get('port', 3306),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True # 자동 커밋 설정
        )
        return connection
    except pymysql.MySQLError as e:
        print(f"ERROR: Database connection failed: {e}")
        return None

# --------------------------------------------------------------------------- #
# API 엔드포인트
# --------------------------------------------------------------------------- #
@app.route('/log/order', methods=['POST'])
def log_order():
    """주문 관련 로그를 DB에 기록합니다."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed"}), 500

    try:
        with conn.cursor() as cursor:
            # 'details' 필드가 dict인 경우 JSON 문자열로 변환
            if 'details' in data and isinstance(data['details'], dict):
                data['details'] = json.dumps(data['details'])

            sql = """
                INSERT INTO templates.order_logs (
                    installation_id, order_id, order_number, menu_name, status, details
                ) VALUES (
                    %(installation_id)s, %(order_id)s, %(order_number)s, %(menu_name)s, %(status)s, %(details)s
                )
            """
            params = {
                "installation_id": INSTALLATION_ID,
                "order_id": data.get('order_id'),
                "order_number": data.get('order_number'),
                "menu_name": data.get('menu_name'),
                "status": data.get('status'),
                "details": data.get('details')
            }
            cursor.execute(sql, params)
        return jsonify({"status": "success"}), 201
    except pymysql.MySQLError as e:
        print(f"ERROR: Failed to insert order log: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/log/event', methods=['POST'])
def log_event():
    """시스템 이벤트 로그를 DB에 기록합니다."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed"}), 500

    try:
        with conn.cursor() as cursor:
            # 'details' 필드가 dict인 경우 JSON 문자열로 변환
            if 'details' in data and isinstance(data['details'], dict):
                data['details'] = json.dumps(data['details'])

            sql = """
                INSERT INTO templates.event_logs (
                    installation_id, event_type, component, level, message, details
                ) VALUES (
                    %(installation_id)s, %(event_type)s, %(component)s, %(level)s, %(message)s, %(details)s
                )
            """
            params = {
                "installation_id": INSTALLATION_ID,
                "event_type": data.get('event_type'),
                "component": data.get('component'),
                "level": data.get('level', 'INFO'),
                "message": data.get('message'),
                "details": data.get('details')
            }
            cursor.execute(sql, params)
        return jsonify({"status": "success"}), 201
    except pymysql.MySQLError as e:
        print(f"ERROR: Failed to insert event log: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --------------------------------------------------------------------------- #
# 서버 실행
# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    # 서비스 포트 맵핑 규칙에 따라 8800 포트 사용
    app.run(host='0.0.0.0', port=8800, debug=False)

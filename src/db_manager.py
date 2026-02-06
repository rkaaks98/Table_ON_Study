import pymysql
import json
import logging

logger = logging.getLogger("RobotServer")

class DBManager:
    def __init__(self, host='localhost', user='root', password='your_password', dbname='tableon_study'):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': dbname,
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor,
            'autocommit': True
        }
        self.init_tables()

    def get_connection(self):
        """DB 커넥션을 생성하여 반환"""
        try:
            return pymysql.connect(**self.config)
        except Exception as e:
            logger.error(f"[DB] Connection Failed: {e}")
            return None

    def init_tables(self):
        """필요한 테이블 생성 (최초 1회)"""
        conn = self.get_connection()
        if not conn: return
        
        try:
            with conn.cursor() as cursor:
                # 1. 주문 로그 테이블 (원본 order_logs 참고)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS order_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        order_id VARCHAR(50),
                        menu_name VARCHAR(100),
                        status VARCHAR(50),
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # 2. 픽업 슬롯 상태 테이블
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pickup_slots (
                        slot_id INT PRIMARY KEY,
                        is_occupied TINYINT(1) DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                ''')
                # 초기 데이터 (1~4번 슬롯)
                cursor.execute("SELECT COUNT(*) as count FROM pickup_slots")
                if cursor.fetchone()['count'] == 0:
                    for i in range(1, 5):
                        cursor.execute("INSERT INTO pickup_slots (slot_id, is_occupied) VALUES (%s, 0)", (i,))
            logger.info("[DB] Tables initialized successfully")
        except Exception as e:
            logger.error(f"[DB] Table Init Error: {e}")
        finally:
            conn.close()

    def update_slot_status(self, slot_id, occupied):
        """슬롯 상태 업데이트"""
        conn = self.get_connection()
        if not conn: return
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE pickup_slots SET is_occupied = %s WHERE slot_id = %s"
                cursor.execute(sql, (1 if occupied else 0, slot_id))
        finally:
            conn.close()

    def load_pickup_slots(self):
        """DB에서 현재 슬롯 상태 로드"""
        conn = self.get_connection()
        if not conn: return {1: False, 2: False, 3: False, 4: False}
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT slot_id, is_occupied FROM pickup_slots")
                rows = cursor.fetchall()
                return {row['slot_id']: bool(row['is_occupied']) for row in rows}
        finally:
            conn.close()
            
    # src/db_manager.py 파일 안에 추가

    def log_order(self, menu_code, menu_name, status="WAITING", details=None):
        """주문 기록을 DB에 저장합니다."""
        conn = self.get_connection()
        if not conn: return None
        
        try:
            with conn.cursor() as cursor:
                # details가 dict인 경우 JSON 문자열로 변환
                if details and isinstance(details, dict):
                    details = json.dumps(details)
                
                sql = """
                    INSERT INTO order_logs (menu_code, menu_name, status, details)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (menu_code, menu_name, status, details))
                return cursor.lastrowid # 생성된 주문의 ID 반환
        except Exception as e:
            logger.error(f"[DB] Log Order Error: {e}")
            return None
        finally:
            conn.close()
            
    def get_last_order_id(self):
        """마지막 주문 ID를 반환합니다."""
        conn = self.get_connection()
        if not conn: return None
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT MAX(id) as last_id FROM order_logs")
                return cursor.fetchone()['last_id']
        finally:
            conn.close()
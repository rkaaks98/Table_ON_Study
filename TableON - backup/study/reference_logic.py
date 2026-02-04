# =================================================================
# [참고용] TableON 메인 컨트롤러 예시 로직
# 이 파일은 학습을 위해 AI가 작성한 예시 가이드입니다.
# 직접 구현하실 때는 study/main.py를 사용하세요!
# =================================================================

import json
import os
import time

# main.py에 정의된 상수와 클래스를 가져왔다고 가정하고 로직만 구성합니다.
# 실제 실행을 위해서는 main.py의 클래스와 상수가 필요합니다.

def example_main_logic(recipes, robot):
    """
    AI가 제안하는 기본적인 주문 처리 흐름 예시
    """
    print("\n" + "="*30)
    print("  TableON 가이드 시스템")
    print("="*30)
    
    # 1. 메뉴 목록 출력
    for r in recipes:
        print(f"[{r['menu_code']}] {r['menu_name']}")
    
    try:
        while True:
            # 2. 사용자 입력 받기
            choice = input("\n주문 번호 입력 (종료: q): ")
            
            if choice.lower() == 'q':
                break
            
            # 3. 레시피 찾기
            target = None
            for r in recipes:
                if str(r['menu_code']) == choice:
                    target = r
                    break
            
            if target:
                print(f"🔔 주문 확인: {target['menu_name']}")
                
                # 4. 시퀀스 정의 (예시: 1번 -> 4번 -> 5번 동작)
                # 실제로는 레시피의 값을 보고 동적으로 생성해야 합니다.
                sequence = [110, 113, 114, 123] 
                
                # 5. 시퀀스 순차 실행
                success = True
                for cmd in sequence:
                    if robot.send_command(cmd):
                        # 완료 신호(CMD + 500) 대기
                        if not robot.wait_for_init(cmd + 500):
                            print(f"❌ {cmd}번 동작 실패")
                            success = False
                            break
                    else:
                        success = False
                        break
                
                if success:
                    print(f"✅ {target['menu_name']} 제조 완료!")
            else:
                print("❌ 없는 메뉴 번호입니다.")

    except KeyboardInterrupt:
        print("\n중단됨")

if __name__ == "__main__":
    print("이 파일은 참고용 로직 예시입니다. 직접 구현은 main.py에서 진행하세요!")

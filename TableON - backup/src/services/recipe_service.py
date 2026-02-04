# 05.recipeServer.py  (v1 스타일, v2 방식 파일 저장/로드)
from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, threading

app = Flask(__name__)
CORS(app, resources={r"*": {"origins": "*"}})

RECIPE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config', 'recipe.json')

recipes = []                 # [{menu_code:int, cup_num:int, ...}]
recipes_lock = threading.Lock()

# ---------- 유틸 ----------
def load_from_file():
    global recipes
    if os.path.exists(RECIPE_FILE):
        try:
            with open(RECIPE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                with recipes_lock:
                    recipes[:] = data if type(data) == list else []
            print(f"[INFO] 레시피 로드 완료, 항목수 = {len(recipes)}")
        except Exception as e:
            print(f"[ERROR] {RECIPE_FILE} 읽기 실패: {e}")
            recipes[:] = []
    else:
        print(f"[WARN] {RECIPE_FILE} 파일이 없습니다. 빈 리스트로 시작합니다.")
        recipes[:] = []

def save_to_file():
    try:
        with recipes_lock:
            # config 디렉토리가 없으면 생성
            os.makedirs(os.path.dirname(RECIPE_FILE), exist_ok=True)
            with open(RECIPE_FILE, 'w', encoding='utf-8') as f:
                json.dump(recipes, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 레시피 저장 완료, 항목수 = {len(recipes)}")
        return True
    except Exception as e:
        print(f"[ERROR] {RECIPE_FILE} 저장 실패: {e}")
        return False

def find_index_by_menu_code(menu_code):
    for i, r in enumerate(recipes):
        if str(r.get('menu_code')) == str(menu_code):
            return i
    return -1

def to_int(v, default=0):
    try:
        if v is None or v == '':
            return default
        return int(v)
    except:
        return default

def to_float(v, default=0.0):
    try:
        if v is None or v == '':
            return default
        return float(v)
    except:
        return default

def to_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if str(v).lower() in ('true', '1', 'yes', 'y'):
        return True
    if str(v).lower() in ('false', '0', 'no', 'n'):
        return False
    return default

# ---------- API ----------
@app.route('/getAllRecipes', methods=['GET'])
def get_all_recipes():
    with recipes_lock:
        return jsonify(recipes)

@app.route('/getRecipe/<int:menu_code>', methods=['GET'])
def get_recipe(menu_code):
    menu_code = request.args.get('menu_code', '')
    with recipes_lock:
        idx = find_index_by_menu_code(menu_code)
        if idx >= 0:
            return jsonify(recipes[idx])
    return jsonify({})

@app.route('/updateRecipe', methods=['POST'])
def update_recipe():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        mc = data.get('menu_code')
        if mc is None:
            return jsonify({'error': 'menu_code is required'}), 400

        with recipes_lock:
            idx = find_index_by_menu_code(mc)
            
            # 필드 매핑 (입력 데이터 -> 레시피 구조)
            # 없는 필드는 기존 값 유지 또는 기본값
            updated = {
                'menu_code':            to_int(data.get('menu_code')),
                'menu_name':            data.get('menu_name', ''),
                'cup_num':              to_int(data.get('cup_num')),
                'sparkling_ext_time':   to_float(data.get('sparkling_ext_time')),
                'water_ext_time':       to_float(data.get('water_ext_time')),
                'ice_ext_time':         to_float(data.get('ice_ext_time')),
                'hotwater_ext_time':    to_float(data.get('hotwater_ext_time')),
                'icecream_ext_time':    to_float(data.get('icecream_ext_time')),
                'coffee_product_id':    to_int(data.get('coffee_product_id')),
                'coffee_ext_time':      to_float(data.get('coffee_ext_time')),
                'syrups':               data.get('syrups', []), # List of {id, time}
                'milk_boolean':         to_bool(data.get('milk_boolean')),
            }

            if idx >= 0:
                # Update existing
                cur = recipes[idx]
                # Merge: Only update fields present in request if needed, 
                # but for full update usually we overwrite. 
                # Let's overwrite with the prepared 'updated' dict but preserve any extra fields if any.
                cur.update(updated)
                recipes[idx] = cur
                action = "수정"
            else:
                # Add new
                if not updated['menu_name']:
                    updated['menu_name'] = str(updated['menu_code'])
                recipes.append(updated)
                action = "추가"

            print(f"[INFO] updateRecipe -> {action}: {updated.get('menu_code')}")

        ok = save_to_file()
        return jsonify({'message': 'OK', 'action': action}) if ok else (jsonify({'error': 'SAVE_FAIL'}), 500)
        
    except Exception as e:
        print(f"[ERROR] updateRecipe failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/deleteRecipe', methods=['GET'])
def delete_recipe():
    mc = request.args.get('menu_code', '')
    with recipes_lock:
        idx = find_index_by_menu_code(mc)
        if idx >= 0:
            removed = recipes.pop(idx)
            save_to_file()
            print("[INFO] deleteRecipe -> 삭제:", removed.get('menu_code'))
            return "OK"
    return "NOT_FOUND", 404

@app.route('/reload', methods=['GET'])
def reload_recipes():
    
    load_from_file()
    return "OK"

@app.route('/save', methods=['GET'])
def save_recipes():
    
    ok = save_to_file()
    return "OK" if ok else ("SAVE_FAIL", 500)

# ---------- 부팅 ----------
if __name__ == '__main__':
    load_from_file()
    # 포트 충돌 시 바꿔 사용 가능
    app.run(host='0.0.0.0', port=8200, debug=False)

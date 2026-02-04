# src/services/did_service.py
from flask import Flask, render_template
import os

# 웹 파일(templates, static)의 기본 경로를 web 디렉토리로 설정
template_dir = os.path.abspath('/home/TableON/web/templates')
static_dir = os.path.abspath('/home/TableON/web/static')

# template_dir = os.path.abspath('./web/templates')
# static_dir = os.path.abspath('./web/static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

@app.route('/web')
def web():
   return render_template('DID2.html')

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=9100, debug=False)
import requests
import random
import time
import sys

# Order Service URL
BASE_URL = "http://localhost:8100"

# Menu Candidates (From recipe.json)
# 1~17 covers Coffee, Latte, Ade, Tea, IceCream
MENU_CODES = list(range(1, 18))

def send_order(order_no, menu_code):
    try:
        url = f"{BASE_URL}/addOrder/{order_no}/{menu_code}"
        res = requests.get(url, timeout=2)
        if res.status_code == 200:
            print(f"[StressTest] Order {order_no} (Menu {menu_code}) Sent: OK")
        else:
            print(f"[StressTest] Order {order_no} (Menu {menu_code}) Failed: {res.status_code}")
    except Exception as e:
        print(f"[StressTest] Request Error: {e}")

def run_test(count=200, delay=0.2):
    print(f"Starting Stress Test: {count} orders (Delay: {delay}s)...")
    
    # Start order number from 7000 to distinguish from manual orders
    start_no = 7000  
    
    for i in range(count):
        order_no = start_no + i
        menu_code = random.choice(MENU_CODES)
        
        send_order(order_no, menu_code)
        
        if delay > 0:
            time.sleep(delay)
            
    print("Stress Test Completed.")

if __name__ == "__main__":
    # Default settings
    count = 3
    delay = 0.2
    
    # Simple args: python stress_test.py [count] [delay]
    if len(sys.argv) > 1:
        count = int(sys.argv[1])
    if len(sys.argv) > 2:
        delay = float(sys.argv[2])
        
    run_test(count, delay)


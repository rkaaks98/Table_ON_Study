import os
import time
import threading
from datetime import datetime

class TraceLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TraceLogger, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self.start_time = time.time()
        self.log_dir = "logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        # Create a new trace file with timestamp
        filename = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.filepath = os.path.join(self.log_dir, filename)
        
        # Write Header
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write("TimeOffset|Actor|Event|TaskID|CMD|Target|Params|UUID\n")

    def log(self, actor, event, task_id, cmd_code, target, params, uuid=""):
        """
        Log a trace event.
        TimeOffset: Seconds from start (float, 2 decimals)
        Actor: R1, R2, SCH (Scheduler), ORD (Order)
        Event: START, DONE, SKIP, QUEUE, ERROR
        TaskID: T1, T2...
        CMD: 113, 130...
        Target: COFFEE, CUP...
        Params: Key=Value string
        UUID: Order UUID
        """
        try:
            current_time = time.time()
            offset = current_time - self.start_time
            
            # Format params to be compact
            if isinstance(params, dict):
                param_str = ",".join([f"{k}={v}" for k, v in params.items()])
            else:
                param_str = str(params)

            line = f"{offset:.2f}|{actor}|{event}|{task_id}|{cmd_code}|{target}|{param_str}|{uuid}\n"
            
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            print(f"[TraceLogger] Failed to log: {e}")

    def reset(self):
        self.start_time = time.time()


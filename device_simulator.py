# device_simulator.py
import time, random, requests, os
from datetime import datetime

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000")
INGEST = f"{BASE}/v1/device/ingest"

def random_vitals():
    return {
        "ts": datetime.utcnow().isoformat(),
        "bp_systolic": random.randint(100, 140),
        "bp_diastolic": random.randint(60, 95),
        "temperature": round(random.uniform(36.0, 38.5), 1),
        "glucose": round(random.uniform(70, 160), 1),
        "spo2": round(random.uniform(92, 99), 1),
        "steps": random.randint(0, 20),
        "calories": round(random.uniform(0.5, 5.0), 2),
        "sleep_quality": round(random.uniform(0.0, 1.0), 2),
        "heart_rate": random.randint(55, 110)
    }

if __name__ == "__main__":
    print("Device simulator starting. Posting every 60 seconds to", INGEST)
    while True:
        p = random_vitals()
        try:
            r = requests.post(INGEST, json=p, timeout=10)
            print("POST", r.status_code, r.text)
        except Exception as e:
            print("Error posting:", e)
        time.sleep(60)

import cv2, json, os, threading, time
import psutil, requests, websocket
from dotenv import load_dotenv

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("[GPIO] RPi.GPIO not found — running in local mode")
    GPIO_AVAILABLE = False

load_dotenv()

SERVER_URL   = os.getenv("SERVER_URL", "http://192.168.137.1:8000")
WS_URL       = SERVER_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/pi"
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))

print(f"[CONFIG] SERVER_URL    = {SERVER_URL}")
print(f"[CONFIG] CAMERA_INDEX  = {CAMERA_INDEX}")

# ── Buzzer ────────────────────────────────────────────────────────────────────
BUZZER_PIN   = 17
buzzer_stop  = threading.Event()
buzzer_lock  = threading.Lock()
buzzer_running = False

if GPIO_AVAILABLE:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.HIGH)  # HIGH = tắt (active-low buzzer)

def _buzzer_loop(on_time=0.5, off_time=0.3):
    global buzzer_running
    buzzer_stop.clear()
    try:
        while not buzzer_stop.is_set():
            if GPIO_AVAILABLE:
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                time.sleep(on_time)
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                time.sleep(off_time)
            else:
                print("[LOCAL] *BEEP*")
                time.sleep(on_time + off_time)
    except Exception as e:
        print(f"[BUZZER] Error: {e}")
    finally:
        if GPIO_AVAILABLE:
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
        with buzzer_lock:
            buzzer_running = False
        print("[BUZZER] Stopped")

def start_buzzer():
    global buzzer_running
    with buzzer_lock:
        if buzzer_running:
            return
        buzzer_running = True
    threading.Thread(target=_buzzer_loop, daemon=True).start()

def stop_buzzer():
    buzzer_stop.set()

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_RESOLUTION = (640, 480)
CAMERA_FPS        = 15

latest_frame = None
frame_lock   = threading.Lock()

def capture_frames():
    global latest_frame
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_RESOLUTION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
    cap.set(cv2.CAP_PROP_FPS,          CAMERA_FPS)
    if not cap.isOpened():
        print("[CAMERA] Failed to open")
        return
    print("[CAMERA] Started")
    while True:
        ret, frame = cap.read()
        if ret:
            with frame_lock:
                latest_frame = frame

# ── Metrics ───────────────────────────────────────────────────────────────────
def send_metrics():
    fail_count = 0
    while True:
        try:
            data = {"cpu": psutil.cpu_percent(interval=1), "memory": psutil.virtual_memory().percent}
            requests.post(f"{SERVER_URL}/metrics", json=data, timeout=5)
            if fail_count > 0:
                print("[METRICS] Reconnected")
            fail_count = 0
        except Exception:
            fail_count += 1
            if fail_count == 1:
                print("[METRICS] Server unreachable, retrying silently...")
        time.sleep(2 if fail_count == 0 else min(30, 2 * fail_count))

# ── WebSocket ─────────────────────────────────────────────────────────────────
def on_message(ws, message):
    event = json.loads(message).get("event")
    if event == "FALL":
        print("[FALL] Detected — activating buzzer")
        start_buzzer()
    elif event == "RESET":
        print("[RESET] Alarm reset by operator")
        stop_buzzer()

def on_error(ws, error):
    print(f"[WS] Error: {error}")

def on_close(ws, *_):
    print("[WS] Closed")

def stream_to_server():
    def push_frames(ws):
        print("[WS] Streaming frames...")
        while True:
            with frame_lock:
                frame = latest_frame.copy() if latest_frame is not None else None
            if frame is not None:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                try:
                    ws.send(buf.tobytes(), opcode=websocket.ABNF.OPCODE_BINARY)
                except websocket.WebSocketConnectionClosedException:
                    print("[WS] Connection closed")
                    break
            time.sleep(1 / CAMERA_FPS)

    def on_open(ws):
        print(f"[WS] Connected to {WS_URL}")
        threading.Thread(target=push_frames, args=(ws,), daemon=True).start()

    print(f"[WS] Connecting to {WS_URL} ...")
    ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message,
                                on_error=on_error, on_close=on_close)
    ws.run_forever()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    threading.Thread(target=capture_frames, daemon=True).start()
    threading.Thread(target=send_metrics,   daemon=True).start()
    while True:
        stream_to_server()
        print("[WS] Reconnecting in 3s...")
        time.sleep(3)

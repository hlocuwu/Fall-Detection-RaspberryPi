# Fall Detection System — NT532.Q21 Group 02 UIT

Hệ thống phát hiện té ngã sử dụng MediaPipe Pose trên Raspberry Pi, stream video qua WebSocket về server AI, cảnh báo qua Telegram và còi buzzer.

## Kiến trúc hệ thống

```
Raspberry Pi  ──WebSocket──►  AWS EC2 Server  ──►  Web Dashboard
  camera                       AI inference          (Firebase Auth)
  buzzer                       Telegram alert
                                GCS / local log
```

---

## Cấu hình biến môi trường

### Server (AWS EC2) — file `.env`

```env
TELEGRAM_TOKEN=<token từ @BotFather>
TELEGRAM_CHAT_ID=<chat id của bạn>

# Tuỳ chọn — nếu muốn upload ảnh lên Google Cloud Storage
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Client (Raspberry Pi) — file `.env`

```env
SERVER_URL=http://<EC2-PUBLIC-IP>:8000
CAMERA_INDEX=1
```

> `.env` không được commit lên repo. Tạo thủ công trên từng máy.

---

## Khởi chạy Server (AWS EC2 — Ubuntu 22.04/24.04)

```bash
# 1. Clone repo
git clone <repo-url>
cd Fall-Detection-RaspberryPi

# 2. Tạo virtual environment
  python3 -m venv .venv
source .venv/bin/activate

# 3. Cài dependencies
pip install -r requirements.txt

# 4. Tạo file .env (xem mục cấu hình bên trên)
nano .env

# 5. Chạy server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

**Chạy như service (tự restart khi crash):**

```bash
sudo nano /etc/systemd/system/falldetect.service
```

```ini
[Unit]
Description=Fall Detection Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Fall-Detection-RaspberryPi
ExecStart=/home/ubuntu/Fall-Detection-RaspberryPi/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable falldetect
sudo systemctl start falldetect

# Xem log
sudo journalctl -u falldetect -f
```

**Lưu ý AWS Security Group:** Mở inbound TCP port **8000**, source `0.0.0.0/0`.

**Firebase Authorized Domains:** Thêm IP public EC2 vào Firebase Console → Authentication → Settings → Authorized domains.

---

## Khởi chạy Client (Raspberry Pi)

```bash
# 1. Clone repo
git clone <repo-url>
cd Fall-Detection-RaspberryPi

# 2. Cài dependencies
pip install -r requirements.txt
pip install RPi.GPIO

# 3. Tạo file .env
nano .env

# 4. Tắt còi trước khi chạy (buzzer kêu lúc mới cắm nguồn)
python3 -c "import RPi.GPIO as GPIO; GPIO.setwarnings(False); GPIO.setmode(GPIO.BCM); GPIO.setup(17, GPIO.OUT); GPIO.output(17, GPIO.HIGH)"

# 5. Chạy client
python3 client.py
```

**Tự tắt còi khi boot (crontab):**

```bash
crontab -e
# Thêm dòng:
@reboot python3 /home/pi/Fall-Detection-RaspberryPi/buzzer_off.py
```

---

## Sơ đồ nối dây Buzzer (Active-Low, Low Level Trigger)

```
Raspberry Pi GPIO Header (nhìn từ trên)

        3.3V  [1] [2]  5V
       GPIO2  [3] [4]  5V
       GPIO3  [5] [6]  GND
       GPIO4  [7] [8]  GPIO14
         GND  [9] [10] GPIO15
      GPIO17 [11] [12] GPIO18
               ↑
           I/O còi

Kết nối:
  Còi VCC  →  Pin 1  (3.3V)
  Còi GND  →  Pin 6  (GND)
  Còi I/O  →  Pin 11 (GPIO17)

Logic:
  GPIO17 HIGH  =  còi TẮT  (trạng thái mặc định)
  GPIO17 LOW   =  còi KÊU  (khi phát hiện ngã)
```

---

## Cấu trúc thư mục

```
Fall-Detection-RaspberryPi/
├── server.py            # FastAPI server — AI inference, WebSocket, API
├── client.py            # Raspberry Pi client — camera, buzzer, metrics
├── buzzer_off.py        # Script tắt còi khi boot
├── fall_log.json        # Log timestamp các sự kiện ngã (persist qua restart)
├── requirements.txt     # Python dependencies
├── .env                 # Biến môi trường (không commit)
├── custom/
│   ├── styles.css
│   ├── firebase-config.js
│   └── auth-guard.js
└── templates/
    ├── login.html       # Trang đăng nhập Firebase
    ├── index.html       # Dashboard
    ├── camera.html      # Live camera monitor
    ├── chart.html       # System metrics (CPU, RAM)
    └── fallchart.html   # Fall statistics
```

---

## Lấy Telegram credentials

1. Tìm **@BotFather** trên Telegram → `/newbot` → lấy `TELEGRAM_TOKEN`
2. Gửi tin nhắn bất kỳ cho bot vừa tạo
3. Mở `https://api.telegram.org/bot<TOKEN>/getUpdates` → lấy `chat.id`

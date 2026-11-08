import argparse
import io
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:
    SMBus = None
    i2c_msg = None


class CameraManager:
    """Менеджер захвата видео с аппаратной камеры Raspberry Pi.

    Поддерживает:
    1. Picamera2 (современный стандарт Raspberry Pi OS Bullseye / Bookworm).
    2. OpenCV VideoCapture (V4L2 / USB / libcamerify).
    3. PiCamera (legacy Raspberry Pi OS Buster и старше).
    4. Синтетический поток-заглушку при отсутствии физической камеры.
    """

    def __init__(self, width=640, height=480, framerate=25):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.backend = None
        self.backend_name = "None"
        self._init_camera()

    def _init_camera(self):
        # 1. Попытка инициализации Picamera2 (официальная библиотека Raspberry Pi)
        try:
            from picamera2 import Picamera2

            picam2 = Picamera2()
            config = picam2.create_video_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            picam2.configure(config)
            picam2.start()
            self.backend = picam2
            self.backend_name = "Picamera2"
            print("Камера успешно запущена через Picamera2", flush=True)
            return
        except Exception:
            pass

        # 2. Попытка инициализации через OpenCV (V4L2 / /dev/video0)
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.backend = cap
                self.backend_name = "OpenCV (V4L2)"
                print("Камера успешно запущена через OpenCV (/dev/video0)", flush=True)
                return
            cap.release()
        except Exception:
            pass

        # 3. Попытка инициализации через legacy PiCamera
        try:
            import picamera

            camera = picamera.PiCamera()
            camera.resolution = (self.width, self.height)
            camera.framerate = self.framerate
            self.backend = camera
            self.backend_name = "PiCamera (Legacy)"
            print("Камера успешно запущена через legacy PiCamera", flush=True)
            return
        except Exception:
            pass

        # 4. Резервная заглушка при отсутствии подключенной камеры
        self.backend_name = "Placeholder"
        print("Камера не найдена на устройстве. Включен генератор тестового видеопотока.", flush=True)

    def get_frame(self):
        """Возвращает сжатый кадр в формате JPEG (bytes)."""
        if self.backend_name == "Picamera2":
            stream = io.BytesIO()
            self.backend.capture_file(stream, format="jpeg")
            return stream.getvalue()

        if self.backend_name == "OpenCV (V4L2)":
            import cv2

            ret, frame = self.backend.read()
            if ret:
                _, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                return jpeg.tobytes()

        if self.backend_name == "PiCamera (Legacy)":
            stream = io.BytesIO()
            self.backend.capture(stream, format="jpeg", use_video_port=True)
            return stream.getvalue()

        # Генерация тестового кадра, если камеры физически нет
        return self._create_placeholder_frame()

    def _create_placeholder_frame(self):
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (self.width, self.height), color=(30, 30, 30))
            draw = ImageDraw.Draw(img)
            text = f"OmegaBot Cam\n[Test Pattern]\n{time.strftime('%H:%M:%S')}"
            draw.text((self.width // 4, self.height // 3), text, fill=(220, 220, 220))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
        except Exception:
            # Минимальный валидный JPEG-кадр 1x1 px при отсутствии PIL
            return (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08"
                b"\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13"
                b"\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff"
                b"\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01"
                b"\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
                b"\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
            )

    def close(self):
        if self.backend_name == "Picamera2" and self.backend:
            try:
                self.backend.stop()
            except Exception:
                pass
        elif self.backend_name == "OpenCV (V4L2)" and self.backend:
            try:
                self.backend.release()
            except Exception:
                pass
        elif self.backend_name == "PiCamera (Legacy)" and self.backend:
            try:
                self.backend.close()
            except Exception:
                pass


class StreamingHandler(BaseHTTPRequestHandler):
    """Обработчик HTTP-запросов для трансляции MJPEG видеопотока."""

    def do_GET(self):
        if self.path in ("/", "/stream.mjpg", "/video"):
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while getattr(self.server, "running", True):
                    frame = self.server.camera.get_frame()
                    if frame:
                        self.wfile.write(b"--FRAME\r\n")
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(frame)))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    time.sleep(1.0 / self.server.camera.framerate)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Отключаем спам HTTP-логов в консоль
        pass


class VideoStreamServer(ThreadingHTTPServer):
    def __init__(self, server_address, camera):
        super().__init__(server_address, StreamingHandler)
        self.camera = camera
        self.running = True


def start_video_server(host, port, camera):
    server = VideoStreamServer((host, port), camera)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Видеосервер (MJPEG) запущен на http://{host}:{port}/stream.mjpg", flush=True)
    return server


def normalize_command(line):
    parts = line.strip().split()
    if parts == ["STOP"]:
        return "STOP"
    if len(parts) != 3 or parts[0] != "DRIVE":
        return None

    try:
        left, right = int(parts[1]), int(parts[2])
    except ValueError:
        return None

    if all(-100 <= speed <= 100 for speed in (left, right)):
        return f"DRIVE {left} {right}"
    return None


def send_i2c(bus, address, command):
    try:
        message = i2c_msg.write(address, command.encode("ascii"))
        bus.i2c_rdwr(message)
        print(f"I2C: {command}", flush=True)
    except OSError as error:
        print(f"Ошибка передачи I2C [{command}]: {error}", flush=True)


def handle_client(connection, client_address, bus, arduino_address):
    print(f"Подключён компьютер управления: {client_address[0]}", flush=True)
    try:
        with connection, connection.makefile("r", encoding="utf-8") as stream:
            for line in stream:
                command = normalize_command(line)
                if command is not None:
                    send_i2c(bus, arduino_address, command)
    finally:
        send_i2c(bus, arduino_address, "STOP")
        print(f"Компьютер управления отключён: {client_address[0]}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Сервер управления и видеостриминга OmegaBot")
    parser.add_argument("--port", type=int, default=5000, help="TCP порт команд управления (default: 5000)")
    parser.add_argument("--video-port", type=int, default=5001, help="HTTP порт MJPEG видеопотока (default: 5001)")
    parser.add_argument("--no-video", action="store_true", help="Отключить видеостриминг")
    parser.add_argument("--i2c-bus", type=int, default=1, help="Номер шины I2C (default: 1)")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x08, help="I2C адрес Arduino (default: 0x08)")
    return parser.parse_args()


def main():
    args = parse_args()
    print("Запуск raspberry_server.py (Команды + Камера)", flush=True)

    video_server = None
    camera = None
    if not args.no_video:
        camera = CameraManager()
        video_server = start_video_server("0.0.0.0", args.video_port, camera)

    if SMBus is None:
        raise SystemExit("Ошибка: библиотека smbus2 не найдена. На Raspberry Pi выполните: pip install smbus2")

    print(f"Открытие I2C bus {args.i2c_bus}", flush=True)
    with SMBus(args.i2c_bus) as bus, socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        print(f"I2C открыта, адрес Arduino: 0x{args.address:02X}", flush=True)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", args.port))
        server.listen(1)
        print(f"Сервер команд ожидает подключения на порту {args.port}", flush=True)
        try:
            while True:
                connection, client_address = server.accept()
                handle_client(connection, client_address, bus, args.address)
        finally:
            send_i2c(bus, args.address, "STOP")
            if video_server:
                video_server.running = False
                video_server.shutdown()
            if camera:
                camera.close()


if __name__ == "__main__":
    main()

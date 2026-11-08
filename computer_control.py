import io
import socket
import threading
import tkinter as tk
from tkinter import messagebox
import urllib.request
from urllib.error import URLError

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


KEY_DIRECTIONS = {
    # Английская раскладка
    "w": "up",
    "s": "down",
    "a": "left",
    "d": "right",
    # Стрелки
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    # Русская раскладка (char и keysym Tkinter)
    "ц": "up",
    "ы": "down",
    "ф": "left",
    "в": "right",
    "cyrillic_tse": "up",
    "cyrillic_yeru": "down",
    "cyrillic_ef": "left",
    "cyrillic_ve": "right",
}


class ControllerApp:
    def __init__(self, root):
        self.root = root
        self.socket = None
        self.pressed = set()

        # Сетевые настройки
        self.host = tk.StringVar(value="192.168.1.50")
        self.control_port = tk.StringVar(value="5000")
        self.video_port = tk.StringVar(value="5001")
        self.enable_video = tk.BooleanVar(value=True)

        # Состояние управления и видео
        self.speed = tk.IntVar(value=50)
        self.status = tk.StringVar(value="Не подключено")
        self.video_status = tk.StringVar(value="Видео отключено")

        # Потоки видео
        self.video_running = False
        self.video_thread = None
        self.video_width = 480
        self.video_height = 360
        self.current_photo = None

        root.title("Управление OmegaBot с видеопотоком")
        root.resizable(False, False)

        self.build_interface()

        # Привязка клавиш управления
        root.bind("<KeyPress>", self.on_key_press)
        root.bind("<KeyRelease>", self.on_key_release)
        root.bind("<KeyPress-space>", lambda event: self.stop())
        root.protocol("WM_DELETE_WINDOW", self.close)

    def build_interface(self):
        main_container = tk.Frame(self.root, padx=10, pady=10)
        main_container.pack(fill="both", expand=True)

        # --- Левая панель: Окно видеопотока с камеры ---
        video_box = tk.LabelFrame(main_container, text="Камера робота (Raspberry Pi)", padx=6, pady=6)
        video_box.grid(row=0, column=0, padx=(0, 10), sticky="n")

        self.video_label = tk.Label(
            video_box,
            text="Видеопоток не подключен\n\nВведите IP и нажмите «Подключиться»",
            bg="#181818",
            fg="#cccccc",
            font=("Arial", 11),
            width=54,
            height=20,
        )
        self.video_label.pack()

        tk.Label(video_box, textvariable=self.video_status, fg="#555555", font=("Arial", 9)).pack(pady=(4, 0))

        # --- Правая панель: Настройки подключения и пульт управления ---
        right_panel = tk.Frame(main_container)
        right_panel.grid(row=0, column=1, sticky="n")

        # Блок подключения
        connection_frame = tk.LabelFrame(right_panel, text="Подключение", padx=10, pady=8)
        connection_frame.pack(fill="x", pady=(0, 8))

        tk.Label(connection_frame, text="IP:").grid(row=0, column=0, sticky="w")
        tk.Entry(connection_frame, textvariable=self.host, width=15).grid(row=0, column=1, padx=4, pady=2)

        tk.Label(connection_frame, text="Порт упр.:").grid(row=1, column=0, sticky="w")
        tk.Entry(connection_frame, textvariable=self.control_port, width=8).grid(row=1, column=1, padx=4, pady=2, sticky="w")

        tk.Label(connection_frame, text="Порт видео:").grid(row=2, column=0, sticky="w")
        tk.Entry(connection_frame, textvariable=self.video_port, width=8).grid(row=2, column=1, padx=4, pady=2, sticky="w")

        tk.Checkbutton(connection_frame, text="Загружать видео", variable=self.enable_video).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(2, 6)
        )

        self.btn_connect = tk.Button(connection_frame, text="Подключиться", bg="#d9ead3", command=self.toggle_connection)
        self.btn_connect.grid(row=4, column=0, columnspan=2, fill="x", pady=2)

        # Регулятор скорости
        speed_frame = tk.LabelFrame(right_panel, text="Скорость (PWM %)", padx=8, pady=6)
        speed_frame.pack(fill="x", pady=(0, 8))

        tk.Scale(
            speed_frame,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.speed,
            length=220,
            command=lambda value: self.on_speed_change(),
        ).pack()

        # Кнопки перемещения
        controls_frame = tk.LabelFrame(right_panel, text="Движение", padx=8, pady=8)
        controls_frame.pack(fill="x", pady=(0, 8))

        btn_grid = tk.Frame(controls_frame)
        btn_grid.pack()

        self.make_button(btn_grid, "↑", "up", 0, 1)
        self.make_button(btn_grid, "←", "left", 1, 0)
        tk.Button(
            btn_grid,
            text="STOP",
            width=6,
            height=2,
            bg="#f4cccc",
            fg="#990000",
            font=("Arial", 9, "bold"),
            command=self.stop,
        ).grid(row=1, column=1, padx=4, pady=4)
        self.make_button(btn_grid, "→", "right", 1, 2)
        self.make_button(btn_grid, "↓", "down", 2, 1)

        # Подсказка и статус
        tk.Label(right_panel, text="WASD / Стрелки — ход\nПробел — STOP", font=("Arial", 9), fg="#666666").pack(pady=2)
        tk.Label(right_panel, textvariable=self.status, font=("Arial", 9, "bold"), wraplength=230).pack(pady=(4, 0))

    def make_button(self, parent, text, direction, row, column):
        button = tk.Button(parent, text=text, width=6, height=2, font=("Arial", 10, "bold"))
        button.grid(row=row, column=column, padx=4, pady=4)
        button.bind("<ButtonPress-1>", lambda event: self.press(direction))
        button.bind("<ButtonRelease-1>", lambda event: self.release(direction))

    def toggle_connection(self):
        if self.socket is not None or self.video_running:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        self.disconnect()
        host = self.host.get().strip()

        # 1. Подключение к серверу команд (TCP)
        try:
            ctrl_port = int(self.control_port.get())
            self.socket = socket.create_connection((host, ctrl_port), timeout=3)
            self.socket.settimeout(None)
            self.status.set(f"Управление: подключено ({host}:{ctrl_port})")
            self.btn_connect.configure(text="Отключиться", bg="#f4cccc")
        except (OSError, ValueError) as error:
            self.socket = None
            self.status.set("Ошибка подключения управления")
            messagebox.showerror("Ошибка подключения управления", str(error))
            return

        # 2. Запуск видеопотока при включенной опции
        if self.enable_video.get():
            self.start_video_stream(host)

        self.root.focus_set()

    def disconnect(self):
        # Остановка видеопотока
        self.stop_video_stream()

        # Остановка управления
        connection = self.socket
        self.socket = None
        self.pressed.clear()
        if connection is not None:
            try:
                connection.sendall(b"STOP\n")
            except OSError:
                pass
            connection.close()

        self.status.set("Не подключено")
        self.btn_connect.configure(text="Подключиться", bg="#d9ead3")

    def start_video_stream(self, host):
        if not PIL_AVAILABLE:
            self.video_status.set("Ошибка: не установлен Pillow (pip install Pillow)")
            self.video_label.configure(
                text="Библиотека Pillow не найдена.\n\nУстановите:\npip install Pillow",
                image="",
            )
            return

        try:
            port = int(self.video_port.get())
        except ValueError:
            self.video_status.set("Неверный порт видео")
            return

        self.video_running = True
        self.video_status.set(f"Подключение видео: http://{host}:{port}/stream.mjpg")
        self.video_thread = threading.Thread(target=self._video_worker, args=(host, port), daemon=True)
        self.video_thread.start()

    def stop_video_stream(self):
        self.video_running = False
        self.video_status.set("Видео отключено")
        self.reset_video_display()

    def _video_worker(self, host, port):
        url = f"http://{host}:{port}/stream.mjpg"
        buffer = b""
        stream = None

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OmegaBotClient"})
            stream = urllib.request.urlopen(req, timeout=4)
            self.root.after(0, lambda: self.video_status.set(f"Видео активно: {host}:{port}"))

            while self.video_running:
                chunk = stream.read(4096)
                if not chunk:
                    break
                buffer += chunk

                # Поиск границы JPEG-кадра (SOI: 0xFFD8, EOI: 0xFFD9)
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9")

                if start != -1 and end != -1 and end > start:
                    jpg_data = buffer[start : end + 2]
                    buffer = buffer[end + 2 :]

                    try:
                        image = Image.open(io.BytesIO(jpg_data))
                        image = image.resize((self.video_width, self.video_height), Image.Resampling.BILINEAR)
                        photo = ImageTk.PhotoImage(image)
                        self.root.after(0, self.update_video_frame, photo)
                    except Exception:
                        pass
        except (URLError, OSError, TimeoutError) as error:
            if self.video_running:
                self.root.after(0, lambda: self.video_status.set(f"Видеопоток прерван: {error}"))
        finally:
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
            self.video_running = False
            self.root.after(0, self.reset_video_display)

    def update_video_frame(self, photo):
        if self.video_running:
            self.current_photo = photo
            self.video_label.configure(image=photo, text="")

    def reset_video_display(self):
        self.current_photo = None
        self.video_label.configure(
            image="",
            text="Видеопоток не подключен\n\nНажмите «Подключиться» для запуска трансляции",
        )

    def send_command(self, command):
        if self.socket is None:
            return
        try:
            self.socket.sendall(f"{command}\n".encode("ascii"))
        except OSError as error:
            self.disconnect()
            self.status.set(f"Соединение потеряно: {error}")

    def press(self, direction):
        if direction not in self.pressed:
            self.pressed.add(direction)
            self.update_drive()

    def release(self, direction):
        if direction in self.pressed:
            self.pressed.remove(direction)
            self.update_drive()

    def on_key_press(self, event):
        if isinstance(self.root.focus_get(), tk.Entry):
            return
        key_char = event.char.lower() if event.char else ""
        direction = KEY_DIRECTIONS.get(event.keysym.lower()) or KEY_DIRECTIONS.get(key_char)
        if direction is not None:
            self.press(direction)

    def on_key_release(self, event):
        key_char = event.char.lower() if event.char else ""
        direction = KEY_DIRECTIONS.get(event.keysym.lower()) or KEY_DIRECTIONS.get(key_char)
        if direction is not None:
            self.release(direction)

    def on_speed_change(self):
        if self.pressed:
            self.update_drive()

    def update_drive(self):
        speed = self.speed.get()
        forward = "up" in self.pressed
        backward = "down" in self.pressed
        left_turn = "left" in self.pressed
        right_turn = "right" in self.pressed

        if not self.pressed:
            self.send_command("STOP")
            return

        base = speed if forward != backward and forward else -speed if forward != backward else 0
        left = right = base

        if left_turn != right_turn:
            if base == 0:
                left = -speed if left_turn else speed
                right = -left
            elif left_turn:
                left = 0
            else:
                right = 0

        if left == 0 and right == 0:
            self.send_command("STOP")
        else:
            self.send_command(f"DRIVE {left} {right}")

    def stop(self):
        self.pressed.clear()
        self.send_command("STOP")

    def close(self):
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    ControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

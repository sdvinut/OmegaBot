#include <Wire.h>

constexpr uint8_t I2C_ADDRESS = 0x08;

// Выводы управления моторами.
// Управление осуществляется разностью напряжений на контактах: V_мотора = V(PIN_A) - V(PIN_B).
// Пины не разделяются на "ШИМ" и "направление" — оба вывода управляются через analogWrite.
constexpr uint8_t LEFT_PIN_A = 7;
constexpr uint8_t LEFT_PIN_B = 6;
constexpr uint8_t RIGHT_PIN_A = 4;
constexpr uint8_t RIGHT_PIN_B = 5;

// Таймаут безопасности (Watchdog): автоматическая остановка моторов,
// если от Raspberry Pi не поступало команд дольше WATCHDOG_TIMEOUT_MS миллисекунд.
constexpr unsigned long WATCHDOG_TIMEOUT_MS = 600;
volatile unsigned long lastCommandTime = 0;
volatile bool isMoving = false;

void stopMotors() {
  analogWrite(LEFT_PIN_A, 0);
  analogWrite(LEFT_PIN_B, 0);
  analogWrite(RIGHT_PIN_A, 0);
  analogWrite(RIGHT_PIN_B, 0);
  isMoving = false;
}

void setMotor(uint8_t pinA, uint8_t pinB, int speed) {
  // Пересчет скорости (-100..100%) в амплитуду напряжения ШИМ (0..255)
  const uint8_t pwm = static_cast<uint8_t>(abs(speed) * 255 / 100);

  if (speed > 0) {
    // Движение вперед: разность потенциалов V(A) - V(B) = pwm - 0 = +pwm
    analogWrite(pinA, pwm);
    analogWrite(pinB, 0);
  } else if (speed < 0) {
    // Движение назад: разность потенциалов V(A) - V(B) = 0 - pwm = -pwm
    analogWrite(pinA, 0);
    analogWrite(pinB, pwm);
  } else {
    // Остановка: разность потенциалов V(A) - V(B) = 0 - 0 = 0
    analogWrite(pinA, 0);
    analogWrite(pinB, 0);
  }
}

void setMotorsSpeed(int leftSpeed, int rightSpeed) {
  setMotor(LEFT_PIN_A, LEFT_PIN_B, leftSpeed);
  setMotor(RIGHT_PIN_A, RIGHT_PIN_B, rightSpeed);
}

bool validSpeed(long speed) {
  return speed >= -100 && speed <= 100;
}

void receiveCommand(int) {
  char command[32] = {0};
  size_t index = 0;

  while (Wire.available()) {
    const char value = static_cast<char>(Wire.read());
    if (index < sizeof(command) - 1) {
      command[index++] = value;
    }
  }

  if (strcmp(command, "STOP") == 0) {
    stopMotors();
    return;
  }

  int leftSpeed;
  int rightSpeed;
  char extra;
  if (sscanf(command, "DRIVE %d %d %c", &leftSpeed, &rightSpeed, &extra) == 2 &&
      validSpeed(leftSpeed) && validSpeed(rightSpeed)) {
    setMotorsSpeed(leftSpeed, rightSpeed);
    lastCommandTime = millis();
    isMoving = (leftSpeed != 0 || rightSpeed != 0);
    return;
  }

  if (strncmp(command, "GO ", 3) == 0) {
    char *end;
    const long speed = strtol(command + 3, &end, 10);
    if (*end == '\0' && validSpeed(speed)) {
      setMotorsSpeed(static_cast<int>(speed), static_cast<int>(speed));
      lastCommandTime = millis();
      isMoving = (speed != 0);
    }
  }
}

void setup() {
  pinMode(LEFT_PIN_A, OUTPUT);
  pinMode(LEFT_PIN_B, OUTPUT);
  pinMode(RIGHT_PIN_A, OUTPUT);
  pinMode(RIGHT_PIN_B, OUTPUT);
  stopMotors();

  Wire.begin(I2C_ADDRESS);
  Wire.onReceive(receiveCommand);
}

void loop() {
  // Аппаратный сторожевой таймер безопасности (Failsafe Watchdog):
  // Если связь прервалась во время движения, моторы гарантированно глушатся.
  if (isMoving && (millis() - lastCommandTime > WATCHDOG_TIMEOUT_MS)) {
    stopMotors();
  }
}

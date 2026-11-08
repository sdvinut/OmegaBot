#include <Wire.h>

constexpr uint8_t I2C_ADDRESS = 0x08;

// Выводы управления моторами: ШИМ (скорость) + Направление (DIR / IN2)
constexpr uint8_t LEFT_PWM = 6;
constexpr uint8_t LEFT_IN2 = 7;
constexpr uint8_t RIGHT_IN2 = 4;
constexpr uint8_t RIGHT_PWM = 5;

void stopMotors() {
  analogWrite(LEFT_PWM, 0);
  analogWrite(RIGHT_PWM, 0);
  digitalWrite(LEFT_IN2, LOW);
  digitalWrite(RIGHT_IN2, LOW);
}

void setMotor(uint8_t pwmPin, uint8_t input2Pin, int speed, uint8_t pwm) {
  if (speed == 0) {
    analogWrite(pwmPin, 0);
    digitalWrite(input2Pin, LOW);
  } else if (speed > 0) {
    digitalWrite(input2Pin, HIGH);
    analogWrite(pwmPin, 255 - pwm);
  } else {
    digitalWrite(input2Pin, LOW);
    analogWrite(pwmPin, pwm);
  }
}

void setMotorsSpeed(int leftSpeed, int rightSpeed) {
  const uint8_t leftPwm = static_cast<uint8_t>(abs(leftSpeed) * 255 / 100);
  const uint8_t rightPwm = static_cast<uint8_t>(abs(rightSpeed) * 255 / 100);
  setMotor(LEFT_PWM, LEFT_IN2, leftSpeed, leftPwm);
  setMotor(RIGHT_PWM, RIGHT_IN2, rightSpeed, rightPwm);
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
    return;
  }

  if (strncmp(command, "GO ", 3) == 0) {
    char *end;
    const long speed = strtol(command + 3, &end, 10);
    if (*end == '\0' && validSpeed(speed)) {
      setMotorsSpeed(static_cast<int>(speed), static_cast<int>(speed));
    }
  }
}

void setup() {
  pinMode(LEFT_PWM, OUTPUT);
  pinMode(LEFT_IN2, OUTPUT);
  pinMode(RIGHT_PWM, OUTPUT);
  pinMode(RIGHT_IN2, OUTPUT);
  stopMotors();

  Wire.begin(I2C_ADDRESS);
  Wire.onReceive(receiveCommand);
}

void loop() {
}

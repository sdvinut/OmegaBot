from smbus2 import SMBus, i2c_msg

I2C_BUS = 1
ARDUINO_ADDRESS = 0x08
COMMAND = b"STOP"

with SMBus(I2C_BUS) as bus:
    bus.i2c_rdwr(i2c_msg.write(ARDUINO_ADDRESS, COMMAND))

print("Команда STOP отправлена")

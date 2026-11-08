import argparse

from smbus2 import SMBus, i2c_msg

I2C_BUS = 1
ARDUINO_ADDRESS = 0x08


def motor_speed(value):
    try:
        speed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("скорость должна быть целым числом") from error

    if not -100 <= speed <= 100:
        raise argparse.ArgumentTypeError("скорость должна быть от -100 до 100")
    return speed


parser = argparse.ArgumentParser(description="Управление моторами OmegaBot")
parser.add_argument("speed", type=motor_speed, help="скорость от -100 до 100")
args = parser.parse_args()

command = b"STOP" if args.speed == 0 else f"GO {args.speed}".encode("ascii")

with SMBus(I2C_BUS) as bus:
    bus.i2c_rdwr(i2c_msg.write(ARDUINO_ADDRESS, command))

print(f"Отправлена команда: {command.decode('ascii')}")

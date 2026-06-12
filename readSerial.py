import serial
import time

# Change this to your serial port
# Linux example: "/dev/ttyUSB0"
# Windows example: "COM3"
PORT = "/dev/ttyUSB0"

BAUD_RATE = 115200

def main():
    try:
        ser = serial.Serial(PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # wait for ESP reset
        print(f"Connected to {PORT} at {BAUD_RATE} baud\n")

        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode(errors="ignore").strip()
                if line:
                    print(line)

    except serial.SerialException as e:
        print("Serial error:", e)

    except KeyboardInterrupt:
        print("\nExiting...")

    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
import logging
from asl_printhead import Driver
import time

logging.basicConfig(level=logging.INFO)		
logger = logging.getLogger("inkjet")
driver_1 = Driver("COM4", logger)
driver_1.power_off()
driver_1.power_on()
print(driver_1.check_head_state(1))
driver_1.set_mode(Driver.Mode.DROPINT)
time.sleep(1)
# Set printhead voltage
driver_1.set_voltage(1, voltage=28)
driver_1.set_frequency(100)
print(driver_1.get_board_status())
# print(driver_1.check_head_state(1))
print("Now polling temperatures...")
temperature_dict = driver_1.check_head_temperatures()
head_1_temp = temperature_dict['head_1']
print(f"Head 1 temperature: {head_1_temp}C")
set_temp = 70
driver_1.set_head_temperature(1, set_temp)
print(f"Setting head 1 temperature to {set_temp}C")
while head_1_temp < (set_temp - 2):
    temperature_dict = driver_1.check_head_temperatures()
    head_1_temp = temperature_dict['head_1']
    print(f"Head 1 temperature: {head_1_temp}C")
    time.sleep(5)

# Activate nozzles for 10 seconds
start_time = time.time()

print("Attempting to print for 10 seconds...")
driver_1.activate_nozzle_span(1, 1, 128)

while time.time() - start_time < 10:
    time.sleep(1)

driver_1.clear_heads()

# If running this script multiple times, leave the power off command commented out.
# This keeps the heater on between runs to stabilize temperature
# On your final run, uncomment the power off command to properly shut down the driver
# driver_1.power_off()

# Terminate listener thread
driver_1.stop_listener()
from PIL import Image
import threading
import numpy
import serial
import time
import json
from enum import IntEnum
import logging

class Driver:
    def __init__(self, port, _logger : logging.Logger, baud_rate=10000000):
        """
        Initializes the serial connection.
        """
        self.ser = serial.Serial(port, baud_rate)
        self.retrun = ""
        self._running = False  # Control flag for the thread
        self.listener_thread = None  # Reference to the thread
        self.json_data = None  # Store parsed JSON data
        self.logger = _logger
        self.logger.info("logger passed to inkjet")
        self.start_listener()

    class Mode(IntEnum):      # numeric values match the firmware cases
        NONE     = 0
        DROPINT  = 1
        DROPEXT  = 2
        STEPPER  = 3
        ENCODER  = 4
        HWPD     = 5

    def power_on(self):
        """
        Powers on the board.
        """
        self.serial_write("O".encode())  # Turn board on
        time.sleep(1)

    def head_reset(self):
        """
        Powers on the board.
        """
        self.serial_write("r".encode())  # Turn board on

    def power_off(self):
        """
        Powers off the board.
        """
        self.serial_write("F".encode())  # Turn board off

    def set_mode(self, mode: "Driver.Mode" = Mode.ENCODER):
        """
        Sets the board’s operating mode.
        """
        self.serial_write(f"M {int(mode)}".encode())  # convert enum → int

    def set_frequency(self, frequency=400):
        """
        Sets the printing frequency.
        """
        self.serial_write(f"p {frequency}".encode())  # Set printing frequency

    def poll_board(self):
        """
        Sets the printing frequency.
        """
        self.serial_write(f"b".encode())  # Set printing frequency

    def set_start_position(self, start_position=1000):
        """
        Sets the start position from the current position.
        """
        self.serial_write(f", {start_position}".encode())  # Set start position

    def set_encoder_reverse(self, reverse = True):
        """
        Sets the start position from the current position.
        """
        if(reverse):
            self.serial_write(f"D 0".encode())  # Set start position
        else:
            self.serial_write(f"D 1".encode())  # Set start position

    def clear_serial_buffer(self):
        """
        Clears the serial buffer.
        """
        while self.ser.in_waiting:
            self.retrun += self.ser.read().decode("utf-8")
        #print(self.retrun)
        self.retrun = ""

    def send_image(self, headIdx, image_path, whiteSpace=0):
        """
        Sends an image to the driver.
        """
        if(headIdx < 1 or headIdx > 4):
            return

        image_to_send = Image.open(image_path)
        image_to_send = image_to_send.rotate(180)
        # Ensure the image is grayscale (convert if needed)
        if image_to_send.mode not in ["L", "1"]:  # "L" is 8-bit grayscale, "1" is binary
            image_to_send = image_to_send.convert("L")  # Convert RGB to grayscale
        width, height = image_to_send.size
        pixel_values = list(image_to_send.getdata())

        pixel_values = (255 - numpy.array(pixel_values).reshape((height, width))) / 255  # Convert to binary

        # Create empty byte array to store image data
        image_data = bytearray()
        image_data.append(87)  # 'W'
        image_data.append(100 + headIdx)  # head index (1-4)

        sumofval, copnt, lasvalu = 0, 0, 0

        # Add whitespace
        for _ in range(whiteSpace):
            for _ in range(16):
                image_data.append(0)
                lasvalu = 0
                sumofval += lasvalu
                copnt += 1

        # Convert image data to binary string
        for i in range(width):
            for byt in range(16):
                cur_byte = 0
                for bit in range(8):
                    j = byt * 8 + bit
                    if pixel_values[j][width-i-1] > 0:
                        cur_byte += 2 ** (7 - bit)
                image_data.append(cur_byte)
                lasvalu = cur_byte
                sumofval += lasvalu
                copnt += 1

        # Time the data send
        t = time.time()

        try:
            self.serial_write(image_data)  # Send image data
        except serial.SerialTimeoutException as e:
            raise RuntimeError(f"Failed to send image data (size: {len(image_data)} bytes) due to a write timeout.") from e

        elapsed = time.time() - t
        self.logger.info(f"Image data sent in {elapsed:.3f}s.")
        time.sleep(0.15)
        self.poll_board()
        time.sleep(0.15)
        receivedData = self.check_image_state(headIdx)  # Poll the board to check if the image was received

        if(receivedData["LV"] == lasvalu):
            if(receivedData["DL"] == copnt):
                if(receivedData["RC"] == sumofval):
                    return True

        return False
    
    def serial_write(self, message):
        try:
            self.ser.write(message)
            self.logger.debug(f"Written:: {message}")
        except:
            self.logger.error(f"Error in sending {message}")
    

    def start_listener(self):
        """
        Starts a thread to listen for incoming data on the serial port.
        """
        if not self._running:
            self._running = True
            self.listener_thread = threading.Thread(target=self._listen_for_data)
            self.listener_thread.start()

    def stop_listener(self):
        """
        Stops the listening thread.
        """
        if self._running:
            self._running = False
            self.listener_thread.join()  # Wait for the thread to finish

    def _listen_for_data(self):
        """
        Private method to continuously listen for incoming data on the serial port.
        """
        buffer = ""
        while self._running:
            if self.ser.in_waiting:
                # Read the data from the serial port
                incoming_data = self.ser.read(self.ser.in_waiting).decode("utf-8")
                #print(incoming_data)
                buffer += incoming_data
                if not buffer.strip().startswith("{"):
                    buffer = ""
                # Detect end of JSON (based on closing '}')
                if buffer.strip().endswith("}"):
                    try:
                        # Parse JSON data
                        self.json_data = json.loads(buffer)
                        #print("JSON data received and parsed:", self.json_data)
                        buffer = ""  # Reset buffer after successful parse
                    except json.JSONDecodeError as e:
                        #print("Error decoding JSON:", e)
                        #print(buffer)
                        buffer = ""  # Reset buffer after successful parse

            time.sleep(0.15)  # Adjust the sleep duration as necessary

    def get_json_element(self, *keys):
        """
        Retrieves a specific element from the parsed JSON data.
        Usage:
            driver.get_json_element('board', 0, 'power') -> returns the power of the board
        """
        self.poll_board()
        time.sleep(0.5)
        if not self.json_data:
            print("No JSON data available")
            return None

        # Navigate through the JSON structure using the keys
        element = self.json_data
        try:
            for key in keys:
                element = element[key]
            return element
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error accessing the element {keys}: {e}")
            return None
        
    def get_board_status(self):
        """Retrieve the latest JSON data."""
        self.poll_board()  # Request data from the board
        time.sleep(0.5)  # Small delay to allow response
        return self.json_data  # Return parsed JSON data
    
    # Helper Methods
    def check_power_status(self):
        """
        Checks the power status of the board.
        Returns True if the power is on, False if off.
        """
        power_status = self.get_json_element('board', 0, 'power')
        if power_status is not None:
            return power_status == 1
        return None

    def check_head_state(self, index):
        """
        Checks the state of a specific head by index.
        Returns a dictionary with head information.
        """
        head_data = self.get_json_element('heads', index - 1)
        if head_data:
            return {
                "voltage": head_data.get('voltage'),
                "status": head_data.get('status'),
                "current_temperature": head_data.get('curTemperature'),
                "set_temperature": head_data.get('setTemperature'),
                "is_heating": head_data.get('isHeating'),
                "is_active": head_data.get('isActive')
            }
        return None
    
    def check_image_state(self, index):
        """
        Checks the state of a specific head by index.
        Returns a dictionary with head information.
        """
        image_data = self.get_json_element('images', index - 1)
        if image_data:
            return {
                "HasImage": image_data.get('dataWaiting') > 0,
                "PixLength": image_data.get('image_stored_dl')/16,
                "InProgress": image_data.get('hasData') > 0,
                "LV": image_data.get('image_stored_lv'),
                "DL": image_data.get('image_stored_dl'),
                "RC": image_data.get('image_stored_rc')
            }
        return None

    def check_image(self, index):
        """
        Checks the state of a specific head by index.
        Returns a dictionary with head information.
        """
        image_data = self.get_json_element('images', index - 1)
        if image_data:
            return {
                "HasImage": image_data.get('dataWaiting') > 0,
                "PixLength": image_data.get('image_stored_dl')/16,
                "InProgress": image_data.get('hasData') > 0
            }
        return None

    def check_encoder_position(self):
        """
        Checks the current encoder position.
        Returns the encoder position.
        """
        encoder_position = self.get_json_element('locations', 0, 'encoder')
        return encoder_position

    def check_print_counts(self, index):
        """
        Checks the print counts of a specific head by index.
        Returns the print count.
        """
        print_counts = self.get_json_element('heads', index - 1, 'printCounts')
        return print_counts

    def __del__(self):
        self._running = False
        self.listener_thread.join()
        print("Background thread killed.")

    def fillHead(self):
        self.serial_write(f"I 1".encode())  # Set start position




# Example usage
if __name__ == "__main__":
    #Example worflow for printing an image
    logging.basicConfig(level=logging.INFO)		
    logger = logging.getLogger("inkjet")
    driver = Driver("COM5", logger)
    driver.power_off()
    driver.power_on()
    print(driver.check_head_state(1))
    driver.set_mode(Driver.Mode.ENCODER)
    driver.set_start_position(1000) ##this is the counts to the start
    if not driver.send_image(1, "test_image.png", whiteSpace=0):
        print("Image send failed.")
        driver.power_off()
    else:
        print("Image sent successfully.")
    print(driver.check_image(1))

    
    
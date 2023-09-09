import signal
import sys
import traceback
import time
from time import sleep
from gbridge import GBridge, GBridgeSocket, GBridgeDebugCommands
import os

import threading

# Default transfer status class.
# If wait is set, the transfers are temporarily stopped.
# If end is set, the transfers are ended.
class TransferStatus:
    def __init__(self):
        self.wait = False
        self.end = False

# Default user output class.
# set_out is called, to "print" the data to the user.
# A program can intercept this, though.
class UserOutput:
    def __init__(self):
        pass

    def set_out(self, string, end='\n'):
        print(string, end=end)

# Default user input class.
# get_input is called, to "get" the user's input.
# A program can use this interface, though.
# Commands are interpreted by interpret_input_keyboard.
class KeyboardThread(threading.Thread):

    def __init__(self):
        super(KeyboardThread, self).__init__()
        self.received = []
        self.daemon = True
        self.received_lock = threading.Lock()
        self.start()

    def run(self):
        while True:
            read_data = input()
            self.received_lock.acquire()
            self.received += [read_data]
            self.received_lock.release()

    def get_input(self):
        self.received_lock.acquire()
        out = self.received
        self.received = []
        self.received_lock.release()
        return out

class SocketThread(threading.Thread):

    def __init__(self, user_output):
        super(SocketThread, self).__init__()
        self.daemon = True
        self.start_processing = False
        self.done_processing = False
        self.bridge = GBridge()
        self.bridge_debug = GBridge()
        self.bridge_sockets = GBridgeSocket(user_output)
        self.lock_in = threading.Lock()
        self.lock_out = threading.Lock()
        self.lock_in.acquire()
        self.lock_out.acquire()
        self.end_run = False
        self.user_output = user_output
        self.start()

    def run(self):
        TRANSFER_FLAGS_MASK = 0xC0
        DEBUG_TRANSFER_FLAG = 0x80
        print_data_in = False
        debug_print = True

        while True:
            self.lock_in.acquire()

            if self.end_run:
                break

            send_list = []
            read_data = self.data
            save_requests = self.save_requests
            ack_requests = self.ack_requests
            num_bytes = int.from_bytes(read_data[:1], byteorder='little')

            curr_bridge = self.bridge
            is_debug = (num_bytes & TRANSFER_FLAGS_MASK) == DEBUG_TRANSFER_FLAG
            if is_debug:
                curr_bridge = self.bridge_debug

            num_bytes &= 0x3F
            bytes = []
            if (num_bytes > 0) and (num_bytes <= (len(read_data) - 1)):
                for i in range(num_bytes):
                    bytes += [int.from_bytes(read_data[(i + 1):(i + 2)], byteorder='little')]

                curr_cmd = True
                if print_data_in and (not is_debug):
                    self.user_output.set_out("IN: " + str(bytes))
                while curr_cmd is not None:
                    curr_cmd = curr_bridge.init_cmd(bytes)
                    if(curr_cmd is not None):
                        bytes = bytes[curr_cmd.total_len - curr_cmd.old_len:]
                        curr_cmd.print_answer(save_requests, ack_requests, self.user_output)
                        if debug_print:
                            curr_cmd.do_print(self.user_output)
                        curr_cmd.check_save(save_requests, self.user_output)
                        if(curr_cmd.response_cmd is not None):
                            send_list += [curr_cmd.response_cmd]
                            if(curr_cmd.process(self.bridge_sockets)):
                                send_list += GBridge.prepare_cmd(curr_cmd.result_to_send(), False)
                                send_list += GBridge.prepare_cmd(curr_cmd.get_if_pending(), True)
            
            self.out_data = send_list

            self.lock_out.release()

    def set_processing(self, data, save_requests, ack_requests):
        self.data = data
        self.save_requests = save_requests
        self.ack_requests = ack_requests

        self.lock_in.release()

    def get_processed(self):
        self.lock_out.acquire()

        return self.out_data

    def end_processing(self):
        self.end_run = True

        self.lock_in.release()

def add_result_debug_commands(actual_cmd, data, debug_send_list, ack_requests):
    result, ack_wanted = GBridgeDebugCommands.load_command(actual_cmd, data)
    debug_send_list += result
    ack_requests[actual_cmd] = ack_wanted
    
    
def interpret_input_keyboard(key_input, debug_send_list, save_requests, ack_requests):
    
    RELAY_TOKEN_SIZE = 0x10

    basic_commands = {
        "GET EEPROM": GBridgeDebugCommands.SEND_EEPROM_CMD,
        "GET STATUS": GBridgeDebugCommands.STATUS_CMD,
        "START ADAPTER": GBridgeDebugCommands.START_CMD,
        "STOP ADAPTER": GBridgeDebugCommands.STOP_CMD,
        "GET NAME": GBridgeDebugCommands.SEND_NAME_INFO_CMD,
        "GET INFO": GBridgeDebugCommands.SEND_OTHER_INFO_CMD,
        "GET NUMBER": GBridgeDebugCommands.SEND_NUMBER_OWN_CMD,
        "GET NUMBER_PEER": GBridgeDebugCommands.SEND_NUMBER_OTHER_CMD,
        "GET RELAY_TOKEN": GBridgeDebugCommands.SEND_RELAY_TOKEN_CMD,
        "FORCE SAVE": GBridgeDebugCommands.FORCE_SAVE_CMD
    }
    
    on_off_commands = {
        "AUTO SAVE": GBridgeDebugCommands.SET_SAVE_STYLE_CMD
    }
    
    mobile_adapter_commands = {
        "SET DEVICE": GBridgeDebugCommands.UPDATE_DEVICE_CMD
    }
    
    unsigned_commands = {
        "SET P2P_PORT": GBridgeDebugCommands.UPDATE_P2P_PORT_CMD
    }
    
    token_commands = {
        "SET RELAY_TOKEN": GBridgeDebugCommands.UPDATE_RELAY_TOKEN_CMD
    }
    
    address_commands = {
        "SET DNS_1": GBridgeDebugCommands.UPDATE_DNS1_CMD,
        "SET DNS_2": GBridgeDebugCommands.UPDATE_DNS2_CMD,
        "SET RELAY": GBridgeDebugCommands.UPDATE_RELAY_CMD,
    }

    path_send_commands = {
        "SAVE EEPROM": GBridgeDebugCommands.SEND_EEPROM_CMD,
        "LOAD EEPROM": GBridgeDebugCommands.UPDATE_EEPROM_CMD
    }

    loading_commands = {
        "LOAD EEPROM"
    }

    saving_commands = {
        "SAVE EEPROM": [GBridge.GBRIDGE_CMD_DEBUG_INFO, GBridgeDebugCommands.CMD_DEBUG_INFO_CFG],
        "SAVE DBG_IN": [GBridge.GBRIDGE_CMD_DEBUG_LOG, GBridgeDebugCommands.CMD_DEBUG_LOG_IN],
        "SAVE DBG_OUT": [GBridge.GBRIDGE_CMD_DEBUG_LOG, GBridgeDebugCommands.CMD_DEBUG_LOG_OUT],
        "SAVE TIME_TR": [GBridge.GBRIDGE_CMD_DEBUG_LOG, GBridgeDebugCommands.CMD_DEBUG_LOG_TIME_TR],
        "SAVE TIME_AC": [GBridge.GBRIDGE_CMD_DEBUG_LOG, GBridgeDebugCommands.CMD_DEBUG_LOG_TIME_AC],
        "SAVE TIME_IR": [GBridge.GBRIDGE_CMD_DEBUG_LOG, GBridgeDebugCommands.CMD_DEBUG_LOG_TIME_IR]
    }
    
    mobile_adapter_types = {
        "BLUE": 8,
        "YELLOW": 9,
        "GREEN": 10,
        "RED": 11
    }

    for elem in key_input.get_input():
        tokens = elem.split()
        command = ""
        if(len(tokens) >= 2):
            command = tokens[0].upper().strip() + " " + tokens[1].upper().strip()

        if command in basic_commands.keys():
            add_result_debug_commands(basic_commands[command], None, debug_send_list, ack_requests)
        
        if command in saving_commands.keys():
            if command in path_send_commands.keys():
                add_result_debug_commands(path_send_commands[command], None, debug_send_list, ack_requests)

            if len(tokens) > 2:
                save_path = tokens[2].strip()
                if saving_commands[command][0] not in save_requests.keys():
                    save_requests[saving_commands[command][0]] = dict()
                save_requests[saving_commands[command][0]][saving_commands[command][1]] = save_path
        
        if command in loading_commands:
            if len(tokens) > 2:
                load_path = tokens[2].strip()
                data = None
                with open(load_path, mode='rb') as file_read:
                    data = file_read.read()
                if data is not None:
                    if command in path_send_commands.keys():
                        add_result_debug_commands(path_send_commands[command], data, debug_send_list, ack_requests)

        if command in mobile_adapter_commands.keys():
            if len(tokens) > 2:
                mobile_type = tokens[2].upper().strip()
                metered = True
                if (len(tokens) > 3) and tokens[3] == "UNMETERED":
                    metered = False
                if mobile_type in mobile_adapter_types.keys():
                    data = mobile_adapter_types[mobile_type]
                    if not metered:
                        data |= 0x80
                    add_result_debug_commands(mobile_adapter_commands[command], data, debug_send_list, ack_requests)

        if command in unsigned_commands.keys():
            if len(tokens) > 2:
                value = GBridgeSocket.parse_unsigned(unsigned_commands[command], tokens[2])
                if value is not None:
                    add_result_debug_commands(unsigned_commands[command], value, debug_send_list, ack_requests)

        if command in address_commands.keys():
            if len(tokens) > 2:
                data = GBridgeSocket.parse_addr(address_commands[command], tokens[2:])
                if data is not None:
                    add_result_debug_commands(address_commands[command], data, debug_send_list, ack_requests)

        if command in on_off_commands.keys():
            if len(tokens) > 2:
                if(tokens[2].upper().strip() == "ON"):
                    add_result_debug_commands(on_off_commands[command], 1, debug_send_list, ack_requests)
                if(tokens[2].upper().strip() == "OFF"):
                    add_result_debug_commands(on_off_commands[command], 0, debug_send_list, ack_requests)

        if command in token_commands.keys():
            if len(tokens) > 2:
                data = []
                try:
                    data = list(bytes.fromhex(tokens[2].upper().strip()))
                except:
                    pass
                if len(data) == RELAY_TOKEN_SIZE:
                    add_result_debug_commands(token_commands[command], [1] + data, debug_send_list, ack_requests)
                elif tokens[2].upper().strip() == "NULL":
                    add_result_debug_commands(token_commands[command], [0], debug_send_list, ack_requests)

def prepare_out_func(analyzed_list, is_debug_cmd, user_output):
    DEBUG_CMD_TRANSFER_FLAG = 0xC0
    print_data_out = False
    limit = 0x40 - 1
    num_elems = 0
    out_buf = []

    if len(analyzed_list) == 0:
        out_buf += [num_elems]
    else:
        num_elems = len(analyzed_list)
        if(num_elems > limit):
            num_elems = limit
        out_val_elems = num_elems
        if is_debug_cmd:
            out_val_elems |= DEBUG_CMD_TRANSFER_FLAG
        out_buf += out_val_elems.to_bytes(1, byteorder='little')
        for i in range(num_elems):
            out_buf += analyzed_list[i].to_bytes(1, byteorder='little')
        if print_data_out:
            user_output.set_out("OUT: " + str(out_buf[1:]))
    return out_buf, num_elems

# Main function, gets the four basic USB connection send/recv functions, the way to get the user input class,
# the transfer state's class and the user output class.
def transfer_func(sender, receiver, list_sender, raw_receiver, pc_commands, transfer_state, user_output):
    out_data_preparer = SocketThread(user_output)
    send_list = []
    debug_send_list = []
    save_requests = dict()
    ack_requests = dict()
    while not transfer_state.end:
        while transfer_state.wait:
            pass
        interpret_input_keyboard(pc_commands, debug_send_list, save_requests, ack_requests)

        if len(send_list) == 0:
            if len(debug_send_list) > 0:
                out_buf, num_elems = prepare_out_func(debug_send_list[0], True, user_output)
                debug_send_list = debug_send_list[1:]
            else:
                out_buf, num_elems = prepare_out_func([], True, user_output)
        else:
            out_buf, num_elems = prepare_out_func(send_list, False, user_output)
            send_list = send_list[num_elems:]
        list_sender(out_buf, chunk_size = len(out_buf))

        out_data_preparer.set_processing(raw_receiver(0x40), save_requests, ack_requests)
        send_list += out_data_preparer.get_processed()
        sleep(0.01)

    out_data_preparer.end_processing()

class LibUSBSendRecv:
    def __init__(self, epOut, epIn, dev, reattach, max_usb_timeout):
        self.epOut = epOut
        self.epIn = epIn
        self.dev = dev
        self.reattach = reattach
        self.max_usb_timeout = max_usb_timeout

    # Code dependant on this connection method
    def sendByte(self, byte_to_send, num_bytes):
        self.epOut.write(byte_to_send.to_bytes(num_bytes, byteorder='big'), timeout=self.max_usb_timeout * 1000)
        return

    # Code dependant on this connection method
    def sendList(self, data, chunk_size=8):
        num_iters = int(len(data)/chunk_size)
        for i in range(num_iters):
            self.epOut.write(data[i*chunk_size:(i+1)*chunk_size], timeout=self.max_usb_timeout * 1000)
        if (num_iters*chunk_size) != len(data):
            self.epOut.write(data[num_iters*chunk_size:], timeout=self.max_usb_timeout * 1000)

    def receiveByte(self, num_bytes):
        recv = int.from_bytes(self.epIn.read(num_bytes, timeout=self.max_usb_timeout * 1000), byteorder='big')
        return recv

    def receiveByte_raw(self, num_bytes):
        return self.epIn.read(num_bytes, timeout=self.max_usb_timeout * 1000)
    
    def kill_function(self):
        import usb.util
        usb.util.dispose_resources(self.dev)
        if(os.name != "nt"):
            if self.reattach:
                self.dev.attach_kernel_driver(0)

class PySerialSendRecv:
    def __init__(self, serial_port):
        self.serial_port = serial_port

    # Code dependant on this connection method
    def sendByte(self, byte_to_send, num_bytes):
        self.serial_port.write(byte_to_send.to_bytes(num_bytes, byteorder='big'))
        return

    # Code dependant on this connection method
    def sendList(self, data, chunk_size=8):
        num_iters = int(len(data)/chunk_size)
        for i in range(num_iters):
            self.serial_port.write(bytes(data[i*chunk_size:(i+1)*chunk_size]))
        if (num_iters*chunk_size) != len(data):
            self.serial_port.write(bytes(data[num_iters*chunk_size:]))

    def receiveByte(self, num_bytes):
        recv = int.from_bytes(self.serial_port.read(num_bytes), byteorder='big')
        return recv

    def receiveByte_raw(self, num_bytes):
        return self.serial_port.read(num_bytes)
    
    def kill_function(self):
        self.serial_port.reset_input_buffer()
        self.serial_port.reset_output_buffer()
        self.serial_port.close()

class WinUSBCDCSendRecv:
    def __init__(self, p):
        self.p = p
        
    # Code dependant on this connection method
    def sendByte(self, byte_to_send, num_bytes):
        self.p.write(byte_to_send.to_bytes(num_bytes, byteorder='big'))

    # Code dependant on this connection method
    def sendList(self, data, chunk_size=8):
        num_iters = int(len(data)/chunk_size)
        for i in range(num_iters):
            self.p.write(bytes(data[i*chunk_size:(i+1)*chunk_size]))
        if (num_iters*chunk_size) != len(data):
            self.p.write(bytes(data[num_iters*chunk_size:]))

    def receiveByte(self, num_bytes):
        recv = int.from_bytes(self.p.read(size=num_bytes), byteorder='big')
        return recv

    def receiveByte_raw(self, num_bytes):
        return self.p.read(size=num_bytes)
    
    def kill_function(self):
        pass

# Things for the USB connection part
def exit_gracefully(usb_handler):
    if usb_handler is not None:
        usb_handler.kill_function()
    os._exit(1)

def libusb_method(VID, PID, max_usb_timeout, user_output):
    import usb.core
    import usb.util
    dev = None
    try:
        devices = list(usb.core.find(find_all=True,idVendor=VID, idProduct=PID))
        for d in devices:
            #user_output.set_out("Device: " + str(d.product))
            dev = d
        if dev is None:
            return None
        reattach = False
        if(os.name != "nt"):
            if dev.is_kernel_driver_active(0):
                try:
                    reattach = True
                    dev.detach_kernel_driver(0)
                except usb.core.USBError as e:
                    sys.exit("Could not detach kernel driver: %s" % str(e))
            else:
                pass
                #user_output.set_out("no kernel driver attached")
        
        dev.reset()

        dev.set_configuration()

        cfg = dev.get_active_configuration()

        intf = cfg[(2,0)]   # Or find interface with class 0xff

        epIn = usb.util.find_descriptor(
            intf,
            custom_match = \
            lambda e: \
                usb.util.endpoint_direction(e.bEndpointAddress) == \
                usb.util.ENDPOINT_IN)

        assert epIn is not None

        epOut = usb.util.find_descriptor(
            intf,
            custom_match = \
            lambda e: \
                usb.util.endpoint_direction(e.bEndpointAddress) == \
                usb.util.ENDPOINT_OUT)

        assert epOut is not None

        dev.ctrl_transfer(bmRequestType = 1, bRequest = 0x22, wIndex = 2, wValue = 0x01)
    except:
        return None
    return LibUSBSendRecv(epOut, epIn, dev, reattach, max_usb_timeout)

def winusbcdc_method(VID, PID, max_usb_timeout, user_output):
    if(os.name == "nt"):
        from winusbcdc import ComPort
        try:
            user_output.set_out("Trying WinUSB CDC")
            p = ComPort(vid=VID, pid=PID)
            if not p.is_open:
                return None
            #p.baudrate = 115200
            p.settimeout(max_usb_timeout)
        except:
            return None
    else:
        return None
    return WinUSBCDCSendRecv(p)

def serial_method(VID, PID, max_usb_timeout, user_output):
    import serial
    import serial.tools.list_ports
    try:
        ports = list(serial.tools.list_ports.comports())
        serial_success = False
        port = None
        for device in ports:
            if(device.vid is not None) and (device.pid is not None):
                if(device.vid == VID) and (device.pid == PID):
                    port = device.device
                    break
        if port is None:
            return None
        serial_port = serial.Serial(port=port, bytesize=8, timeout=0.05, write_timeout = max_usb_timeout)
    except Exception as e:
        return None
    return PySerialSendRecv(serial_port)

# Initial function which sets up the USB connection and then calls the Main function.
# Gets the ending function once the connection ends, then the USB identifiers, and the USB Timeout.
# Also receives the user input class, the transfer state's class and the user output class.
def start_usb_transfer(end_function, VID, PID, max_usb_timeout, pc_commands, transfer_state, user_output, do_ctrl_c_handling=False):
    try_serial = False
    try_libusb = False
    try_winusbcdc = False
    try:
        import usb.core
        import usb.util
        try_libusb = True
    except:
        pass

    if(os.name == "nt"):
        try:
            from winusbcdc import ComPort
            try_winusbcdc = True
        except:
            pass
    try:
        import serial
        import serial.tools.list_ports
        try_serial = True
    except:
        pass

    usb_handler = None

    def signal_handler_ctrl_c(sig, frame):
        user_output.set_out("You pressed Ctrl+C!")
        transfer_state.end = True

    if do_ctrl_c_handling:
        signal.signal(signal.SIGINT, signal_handler_ctrl_c)

    # The execution path
    try:
        if(usb_handler is None) and try_libusb:
            usb_handler = libusb_method(VID, PID, max_usb_timeout, user_output)
        if (usb_handler is None) and try_winusbcdc:
            usb_handler = winusbcdc_method(VID, PID, max_usb_timeout, user_output)
        if (usb_handler is None) and try_serial:
            usb_handler = serial_method(VID, PID, max_usb_timeout, user_output)

        if usb_handler is not None:
            user_output.set_out("USB connection established!")
            transfer_func(usb_handler.sendByte, usb_handler.receiveByte, usb_handler.sendList, usb_handler.receiveByte_raw, pc_commands, transfer_state, user_output)
        else:
            user_output.set_out("Couldn't find USB device!")
            missing = ""
            if not try_serial:
                missing += "PySerial, "
            if not try_libusb:
                missing += "PyUSB, "
            if(os.name == "nt") and (not try_winusbcdc):
                missing += "WinUsbCDC, "
            if missing != "":
                user_output.set_out("If the device is attached, try installing " + missing[:-2])
        
        end_function(usb_handler)
    except:
        #traceback.print_exc()
        user_output.set_out("Unexpected exception: " + str(sys.exc_info()[0]))
        end_function(usb_handler)

if __name__ == "__main__":
    VID = 0xcafe
    PID = 0x4011
    max_usb_timeout = 5
    start_usb_transfer(exit_gracefully, VID, PID, max_usb_timeout, KeyboardThread(), TransferStatus(), UserOutput(), do_ctrl_c_handling=True)

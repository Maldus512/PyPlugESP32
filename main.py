import random as r
import time

import _thread
import machine
import ure
from ujson import dump

READ_TIMEOUT = 1000  # seconds
CONNECTION_TIMEOUT = 5000  # milliseconds

SSID = ''
PSW = ''

reset = False
inLoop = True
regex = None

microCommands = ['ATON', 'ATOFF', 'ATPRINT', 'ATZERO', 'ATRESET', 'ATPOWER', 'ATREAD', 'ATSTATE']
superCommands = ['ATALL', 'ATNET', 'ATREBOOT', 'ATREPL', 'ATTIMER']
acceptedCommands = microCommands + superCommands

timer = {
    'command': '',
    'triggerTimestamp': '',
    'timer': machine.Timer(-1)
}


class ResetException(Exception):
    pass


def setStation():
    '''Set ESP in Station mode. Parameters are network SSID and password.'''

    import network

    sta_if = network.WLAN(network.STA_IF)

    if not sta_if.isconnected():
        print('Connecting to \'{}\'...'.format(SSID))
        sta_if.active(True)
        sta_if.connect(SSID, PSW)

        startTime = time.ticks_ms()  # timeout for the loop below
        while not sta_if.isconnected():
            if time.ticks_diff(time.ticks_ms(), startTime) > CONNECTION_TIMEOUT:
                print('Timeout while connecting to network \'{}\'.'.format(SSID))
                sta_if.active(False)
                return

    print('Network config: {}'.format(sta_if.ifconfig()))


def setAP():
    '''Set ESP in AccesPoint mode. The network name is something like ESP_XXXXXX.'''

    import network
    ap_if = network.WLAN(network.AP_IF)
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(False)
    ap_if.active(True)


def getFromUart(command):
    '''Write a command to the UART bus and return the result value. Accepted commands are:
    - `ATON`: turn relay on
    - `ATOFF`: turn relay off
    - `ATPRINT`: print status informations (every second)
    - `ATZERO`: reset energy consumption counter
    - `ATRESET`: reset any counter
    - `ATPOWER`: get actual power consumption
    - `ATREAD`: get actual current consumption
    - `ATSTATE`: get relay status (0/1)

    Since `uart.read()` is non-blocking, '\\n' is expected as terminating character.'''

    uart = machine.UART(1, baudrate=9600, rx=16, tx=17, timeout=10)

    uart.write(command)

    res = bytes()
    startTime = time.ticks_ms()  # timeout for the loop below
    while b'\n' not in res:
        toAppend = uart.read()

        if toAppend:
            if res != b'':
                res += toAppend
            else:
                res = toAppend

        if time.ticks_diff(time.ticks_ms(), startTime) > READ_TIMEOUT:
            print('ERROR: read timeout')
            return b'ERROR: read timeout'

    res = res.decode('utf-8').replace('\n', '').encode()

    return res


def onClientConnect(conn):
    '''Handle the operations executed by a client. The only parameter is the connection object created by the socket connection.'''

    global reset, regex, inLoop

    reset = False

    try:

        data = conn.recv(256)
        if not data:
            return

        parsedData = data.decode('utf-8').replace('\n', '')
        command = regex.match(parsedData).group(0)
        print("Received command '{}'".format(command))

        res = None

        # pre-process special commands
        if command not in acceptedCommands:
            print("Unknown command '{}'".format(command))

        elif command in microCommands:
            res = getFromUart(data)

        elif command == 'ATALL':
            state = getFromUart(b'ATSTATE\n')
            current = getFromUart(b'ATREAD\n')
            power = getFromUart(b'ATPOWER\n')
            res = state + b',' + current + b',' + power

        elif command == 'ATNET':  # 'ATNET,ssid,password'
            temp = parsedData.split(',')
            ssid = temp[1]
            psw = temp[2]
            if ssid != SSID or psw != PSW:
                with open('network_cfg.py', 'w') as f:
                    f.write('ssid = \'{}\'\npsw = \'{}\''.format(ssid, psw))
                    print('Stored ssid = {} and password = {}'.format(ssid, psw))
                    reset = True

        elif command == 'ATREBOOT':
            reset = True

        elif command == 'ATREPL':
            inLoop = False

        elif command == 'ATTIMER':  # 'ATTIMER,SET/DEL/GET,triggerTimestamp,command
            temp = parsedData.split(',')
            request = temp[1]
            if request == 'SET':
                timer['triggerTimestamp'] = temp[2]
                timer['command'] = temp[3]

                timer['timer'].deinit()

                # period = timer['triggerTimestamp'] -

                # calcola il tempo
                # controlla che non sia gia passato
                # setta il timer come one_shot

                # timer['timer'].init(period=)

            elif request == 'DEL':
                timer = {
                    'command': '',
                    'triggerTimestamp': '',
                    'a': Timer(0)
                }
            else:  # 'GET' and anything else (malformed commands too)
                res = b'{},{}'.format(timer['triggerTimestamp'])

        if res:
            print('Result: {}'.format(res))
            conn.send(res)
    except OSError:
        print('Catched \'OSError')
    except BaseException as e:
        print(str(e))
    finally:
        conn.close()
        print('Connection closed')


def setWakeCondition():
    '''Set wake conditions. Currently:
    - microcontroller is woken up from deep sleep when pin `4` is high.'''

    if machine.wake_reason() == machine.PIN_WAKE:
        print('Woken up')
    else:
        print('Starting')

    wake_pin = machine.Pin(4)
    wake_pin.init()

    wake_pin.irq(trigger=machine.Pin.WAKE_HIGH, wake=machine.DEEPSLEEP)


def main():
    setAP()

    try:
        from network_cfg import ssid, psw
        global SSID, PSW
        SSID = ssid
        PSW = psw
        setStation()
    except ImportError:
        pass

    setWakeCondition()

    import usocket as socket
    import uselect as select

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', '8888'))
    s.listen(5)
    s.settimeout(1)  # accept() timeout

    print('Ready')

    global reset, regex, inLoop

    regex = ure.compile('^AT[A-Z]+')

    try:
        while inLoop:
            if reset:
                raise ResetException

            try:
                # wait to accept a connection - blocking call, but only waits 1 second
                conn, addr = s.accept()
            except OSError:
                # timeout error (and others, but for now it's alright (TODO))
                continue

            conn.settimeout(0.01)  # 10 ms
            print('Connection accepted from {}'.format(addr))
            _thread.start_new_thread(onClientConnect, (conn,))
    except KeyboardInterrupt:
        s.close()
        print('Terminating')
    except ResetException:
        pass
    except BaseException as e:
        print(str(e))
    finally:
        s.close()

        if inLoop:  # if True it means that the loop was not exited consciously
            print('Rebooting')
            machine.reset()
        else:
            print('Entering REPL')

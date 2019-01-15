from time import sleep, time

import _thread
import machine

READ_TIMEOUT = 1  # seconds

acceptedCommands = ['ATON', 'ATOFF', 'ATPRINT', 'ATZERO', 'ATRESET', 'ATPOWER', 'ATREAD', 'ATSTATE'] + ['ATALL']


def setStation(ssid, psw):
    '''Set ESP in Station mode. Parameters are network SSID and password.'''

    import network
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, psw)
        while not sta_if.isconnected():
            pass
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
    startTime = time()  # timeout for the loop below
    while b'\n' not in res:
        toAppend = uart.read()

        if toAppend:
            if res != b'':
                res += toAppend
            else:
                res = toAppend

        if time() - startTime > READ_TIMEOUT:
            print('ERROR: read timeout')
            return b'ERROR: read timeout'

    res = res.decode('utf-8').replace('\n', '').encode()

    return res


def onClientConnect(conn):
    '''Handle the operations executed by a client. The only parameter is the connection object created by the socket connection.'''

    try:
        data = conn.recv(256)
        if not data:
            return

        printableData = data.decode('utf-8').replace('\n', '')
        if printableData not in acceptedCommands:
            print("Unknown command '{}' received".format(printableData))
            conn.close()
            return

        print("Received command '{}'".format(printableData))

        # pre-process special commands
        if printableData == 'ATALL':
            state = getFromUart(b'ATSTATE\n')
            current = getFromUart(b'ATREAD\n')
            power = getFromUart(b'ATPOWER\n')
            res = state + b',' + current + b',' + power
        else:
            res = getFromUart(data)

        print('Result: {}'.format(res))
        if res:
            conn.send(res)
    except OSError:
        print('Catched \'OSError')
    finally:
        conn.close()
        print('Connection closed')


def setWakeCondition():
    '''Set wake conditions. Currently:
    - microcontroller is woken up from deep sleep when pin `4` is high.'''

    if machine.wake_reason() == machine.PIN_WAKE:
        print('Woken up')
    else:
        print('Hello, world!')

    wake_pin = machine.Pin(4)
    wake_pin.init()

    wake_pin.irq(trigger=machine.Pin.WAKE_HIGH, wake=machine.DEEPSLEEP)


def main():
    setAP()
    setWakeCondition()

    print('Starting')

    import usocket as socket
    import uselect as select

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', '8888'))
    s.listen(5)

    try:
        while True:
            # wait to accept a connection - blocking call
            conn, addr = s.accept()
            conn.settimeout(0.01)  # 10 ms
            print('Connection accepted from {}'.format(addr))
            try:
                _thread.start_new_thread(onClientConnect, (conn,))
            except RuntimeError:
                print('Failed to create new thread. Too many? ({})'.format(_thread._count()))
    except BaseException as e:
        print(str(e))
    finally:
        s.close()
        print('Terminating')

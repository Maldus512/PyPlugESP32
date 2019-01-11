from time import sleep

import _thread
import machine

acceptedCommands = ['ATON', 'ATOFF', 'ATPRINT', 'ATZERO', 'ATRESET', 'ATPOWER', 'ATREAD', 'ATSTATE']


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
    '''Write a command to the UART bus and return the result value.Accepted commands are:
    - ATON: turn relay on
    - ATOFF: turn relay off
    - ATPRINT: print status informations (every second)
    - ATZERO: reset energy consumption counter
    - ATRESET: reset any counter
    - ATPOWER: get actual power consumption
    - ATREAD: get actual current consumption
    - ATSTATE: get relay status (0/1)'''

    uart = machine.UART(1, baudrate=9600, rx=16, tx=17, timeout=10)

    uart.write(command)

    # FIXME: this is required in order to wait for uart.write to complete, but it is horrible
    sleep(0.1)  # 100 ms

    uart.write(command)
    res = uart.read()
    if res is None:
        print("Timeout?")

    return res


def onClientConnect(conn):
    '''Handle the operations executed by a client. The only parameter is the connection object created by the socket connection.'''

    try:
        data = conn.recv(256)
        if not data:
            return

        printableData = data.decode("utf-8").replace('\n', '')
        if printableData not in acceptedCommands:
            print("Unknown command '{}' received".format(printableData))
            conn.close()
            return

        print("Received command '{}'".format(printableData))

    except OSError:
        pass

    res = getFromUart(data)
    print(res)
    if res:
        conn.send(res)

    conn.close()
    print('Connection closed')


def setWakeCondition():
    '''Set wake conditions. Currently:
    - microcontroller is woken up from deep sleep when pin 4 is high.'''

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
    s.bind(('', '8888'))
    s.listen(5)

    try:
        while True:
            # wait to accept a connection - blocking call
            conn, addr = s.accept()
            conn.settimeout(0.01)  # 10 ms
            print('Connection accepted from {}'.format(addr))
            _thread.start_new_thread(onClientConnect, (conn,))
    except BaseException:
        pass
    finally:
        s.close()
        print('Terminating')

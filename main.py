import random as r
import time

import _thread
import machine
import network
import ubinascii
import ure
import usocket as socket
from ujson import dump

READ_TIMEOUT = 1000  # milliseconds
CONNECTION_TIMEOUT = 15000  # milliseconds
STATION_ACTIVE_TIMEOUT = 10000  # milliseconds

UDP_PORT = 8889
TCP_PORT = 8888

SSID = None
PSW = None

UUID = None

mustUpdateNetwork = False
reset = False
inLoop = True
regex = None

microCommands = ['ATON', 'ATOFF', 'ATPRINT', 'ATZERO', 'ATRESET', 'ATPOWER', 'ATREAD', 'ATSTATE']
superCommands = ['ATALL', 'ATNET', 'ATREBOOT', 'ATREPL', 'ATTIMER']
acceptedCommands = microCommands + superCommands

_timer = {
    'command': None,
    'triggerTicks': -1,
    'timer': machine.Timer(-1)
}


class ResetException(Exception):
    pass


def setStation():
    '''Set ESP in Station mode. Parameters are network SSID and password.'''

    sta_if = network.WLAN(network.STA_IF)
    print('[setStation] active: {}, connected: {}'.format(sta_if.active(), sta_if.isconnected()))

    if not sta_if.isconnected():
        print('Connecting to \'{}\'...'.format(SSID))
        setActiveSecure(interface=network.STA_IF, active=True)
        sta_if.connect(SSID, PSW)

        startTime = time.ticks_ms()  # timeout for the loop below
        while not sta_if.isconnected():
            if time.ticks_diff(time.ticks_ms(), startTime) > CONNECTION_TIMEOUT:
                print('Timeout while connecting to network \'{}\'.'.format(SSID))
                setActiveSecure(interface=network.STA_IF, active=False)
                print('Enabling AP.')
                setAP()
                return False

    print('Connected to \'{}\''.format(SSID))
    print('STA config: {}'.format(sta_if.ifconfig()))

    print('Disabling AP.')
    setActiveSecure(interface=network.AP_IF, active=False)

    return True


def setAP(disableStation=False):
    '''Set ESP in AccesPoint mode. The network name is something like ESP_XXXXXX.'''

    ap_if = network.WLAN(network.AP_IF)
    setActiveSecure(interface=network.AP_IF, active=False)
    if disableStation:
        setActiveSecure(interface=network.STA_IF, active=False)
    setActiveSecure(interface=network.AP_IF, active=False)
    ap_if.ifconfig()
    print('AP config: {}'.format(ap_if.ifconfig()))


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


def timerGET():
    return str(_timer['triggerTicks']).encode() + b',' + str(_timer['command']).encode()


def networkGET():
    return str(SSID).encode() + b',' + str(PSW).encode()


def onClientConnect(conn):
    '''Handle the operations executed by a client. The only parameter is the connection object created by the socket connection.'''

    global regex

    try:

        data = conn.recv(256)
        if not data:
            return

        parsedData = data.decode('utf-8').replace('\n', '')
        command = regex.match(parsedData).group(0)
        print("Received command '{}'".format(command))

        res = None

        if command not in acceptedCommands:
            print("Unknown command '{}'".format(command))

        # pre-process special commands
        elif command in microCommands:
            res = getFromUart(data)

        elif command == 'ATALL':
            state = getFromUart(b'ATSTATE\n')  # 0
            current = getFromUart(b'ATREAD\n')  # 1
            power = getFromUart(b'ATPOWER\n')  # 2
            timer = timerGET()  # 3 (seconds), 4 (command)
            network = networkGET()  # 5 (ssid), 6 (password)

            res = state + b',' + current + b',' + power + b',' + timer + b',' + network

        elif command == 'ATNET':  # 'ATNET,GET/SET,ssid,password'
            temp = parsedData.split(',')
            request = temp[1]
            if request == 'SET':
                ssid = temp[2]
                psw = temp[3]
                global SSID, PSW, mustUpdateNetwork
                if ssid != SSID or psw != PSW:
                    with open('network_cfg.py', 'w') as f:
                        f.write('ssid = \'{}\'\npsw = \'{}\''.format(ssid, psw))
                        SSID = ssid
                        PSW = psw
                        print('Stored ssid = {} and password = {}'.format(ssid, psw))
                        mustUpdateNetwork = True
            else:
                res = networkGET()

        elif command == 'ATREBOOT':
            with _thread.allocate_lock():
                global reset
                reset = True

        elif command == 'ATREPL':
            with _thread.allocate_lock():
                global inLoop
                inLoop = False

        elif command == 'ATTIMER':  # 'ATTIMER,GET/DEL/SEC,triggerTicks(in seconds),command(ATON/ATOFF)
            global _timer

            temp = parsedData.split(',')
            request = temp[1]
            print('Request: {}'.format(request))
            if request == 'SET':
                _timer['triggerTicks'] = int(temp[2])
                _timer['command'] = temp[3]

                if _timer['command'] not in ['ATON', 'ATOFF']:
                    print('Error: wrong timer command')
                    return

                _timer['timer'].deinit()

                # Set a one-second periodic timer which counts the specified 'triggerTicks'. This
                # is a workaround for always knowing the remaining seconds without using an internet
                # connection for determining the actual calendar date/time.
                _timer['timer'].init(period=1000, mode=machine.Timer.PERIODIC, callback=handleTimerInterrupt)

            elif request == 'DEL':
                _timer['command'] = None
                _timer['triggerTicks'] = -1
                _timer['timer'].deinit()

            else:  # 'GET', and anything else (also malformed ATTIMER commands)
                res = timerGET()

        if res:
            print('Result: {}'.format(res))
            conn.send(res)
    except OSError as e:
        print('### Catched \'OSError. {}'.format(e))
    except BaseException as e:
        print('### {}'.format(e))
    finally:
        conn.close()
        print('Connection closed')


def handleTimerInterrupt(timer):
    global _timer

    if _timer['command'] is None or _timer['triggerTicks'] == -1:
        # this is necessary since, after calling '_timer['timer'].deinit()', the timer will still be called once
        return

    if _timer['triggerTicks'] > 0:
        _timer['triggerTicks'] -= 1
        return

    print('Timer expired')

    if _timer['timer'] is not timer:
        print('Error: inconsistent timers')
        return

    _ = getFromUart((_timer['command'] + '\n').encode())

    _timer['command'] = None
    _timer['triggerTicks'] = -1
    _timer['timer'].deinit()


def generateUUID():
    randomString = ''
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    uuid_format = [8, 4, 4, 4, 12]
    for n in uuid_format:
        for _ in range(0, n):
            randomString += str(chars[r.randint(0, len(chars) - 1)])
        if n != 12:
            randomString += '-'
    return randomString


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


def listenUDP(s):
    print('Started listening for UDP broadcasts.')

    global inLoop, reset

    while inLoop:
        with _thread.allocate_lock():
            try:
                if reset:
                    break

                try:
                    # wait to accept a connection - blocking call, but only waits 1 second
                    msg, addr = s.recvfrom(1024)

                    msg_s = msg.decode()

                    print('[UDP] Received \'{}\' from \'{}\''.format(msg_s, addr))

                    if msg_s == 'ATLOOKUP':
                        sta_if = network.WLAN(network.STA_IF)

                        deviceAddress = ''
                        if sta_if.isconnected():
                            deviceAddress = sta_if.ifconfig()[0]
                        else:
                            ap_if = network.WLAN(network.AP_IF)
                            deviceAddress = ap_if.ifconfig()[0]

                        s.sendto('SOCKET,{},'.format(deviceAddress).encode() + ubinascii.hexlify(network.WLAN().config('mac'), ':') + ',{}'.format(str(TCP_PORT)).encode(), addr)
                    else:
                        print('[UDP] Ignored message \'{}\''.format(msg_s))

                except OSError:
                    # timeout error (and others, but for now it's alright (TODO))
                    continue

            except KeyboardInterrupt:
                with _thread.allocate_lock():
                    inLoop = False
                break
            except BaseException as e:
                print('### [UDP] {}'.format(e))


def setActiveSecure(interface, active):
    '''Sometimes the interface behaved strangely, looking like it wasn't turned off when it was supposed to, and viceversa. This is to ensure that the interface has enough time to actually being turned on/off'''
    # FIXME: maybe there is a better way, I should investigate the problem further.

    _interface = network.WLAN(interface)
    _interface.active(active)
    startTime = time.ticks_ms()  # timeout for the loop below
    while _interface.active() != active:
        if time.ticks_diff(time.ticks_ms(), startTime) > STATION_ACTIVE_TIMEOUT:
            with _thread.allocate_lock():
                global reset
                reset = True


def main():
    global UUID, _timer, reset, regex, inLoop, mustUpdateNetwork

    try:
        from uuid_cfg import uuid as _uuid
        UUID = _uuid
    except ImportError:
        UUID = generateUUID()
        with open('uuid_cfg.py', 'w') as f:
            f.write('uuid = \'{}\'\n'.format(UUID))
        print('Warning: Generated new UUID.')

    print('UUID: {}'.format(UUID))

    socketUDP = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
    socketUDP.bind(('', UDP_PORT))
    socketUDP.settimeout(1)  # accept() timeout

    setActiveSecure(interface=network.STA_IF, active=False)
    setActiveSecure(interface=network.AP_IF, active=False)

    try:
        from network_cfg import ssid, psw
        global SSID, PSW
        SSID = ssid
        PSW = psw
        setStation()
    except ImportError:
        setActiveSecure(interface=network.STA_IF, active=False)
        setAP()

    _thread.start_new_thread(listenUDP, (socketUDP,))

    setWakeCondition()

    socketTCP = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP
    socketTCP.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socketTCP.bind(('', TCP_PORT))
    socketTCP.listen(5)
    socketTCP.settimeout(1)  # accept() timeout

    print('Ready')

    regex = ure.compile('^AT[A-Z]+')

    sta_if = network.WLAN(network.STA_IF)

    while inLoop:
        try:
            if reset:
                raise ResetException
            if mustUpdateNetwork:
                mustUpdateNetwork = False
                setStation()
                raise ResetException

            if sta_if.active() and not sta_if.isconnected():
                setStation()
                continue

            try:
                # wait to accept a connection - blocking call, but only waits 1 second
                conn, addr = socketTCP.accept()
            except OSError:
                # timeout error (and others, but for now it's alright (TODO))
                continue

            conn.settimeout(0.01)  # 10 ms
            print('Connection accepted from {}'.format(addr))
            _thread.start_new_thread(onClientConnect, (conn,))
        except KeyboardInterrupt:
            print('Terminating')
            break
        except ResetException:
            socketTCP.close()
            socketTCP = None
            socketUDP.close()
            socketUDP = None
            _timer['timer'].deinit()
            print('Rebooting')
            machine.reset()
        except BaseException as e:
            print('### {}'.format(e))

    if socketTCP:
        socketTCP.close()
        socketTCP = None
    if socketUDP:
        socketUDP.close()
        socketUDP = None
    _timer['timer'].deinit()
    print('Entering REPL')

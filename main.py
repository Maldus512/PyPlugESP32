import machine


def connect(ssid, psw):
    '''Set ESP in Station mode. Parameters are network SSID and password.'''

    import network
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, psw)
        while not sta_if.isconnected():
            pass
    print('network config:', sta_if.ifconfig())


def setAccessPoint():
    '''Set ESP in AccesPoint mode. The network name is something like ESP_XXXXXX.'''

    import network
    ap_if = network.WLAN(network.AP_IF)
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(False)
    ap_if.active(True)


def pipeCommunication():
    '''Start pipelining commands to the micro-controller. Accepted commands are:
- ATON: turn relay on
- ATOFF: turn relay off
- ATPRINT: print status informations (every second)
- ATZERO: reset energy consumption counter
- ATRESET: reset any counter
- ATPOWER: get actual power consumption
- ATREAD: get actual current consumption
- ATSTATE: get relay status (0/1)'''

    print("Starting pipeline")

    import usocket as socket
    import uselect as select

    uart = machine.UART(1, baudrate=9600, rx=16, tx=17, timeout=10)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', '8888'))
    s.listen(1)

    try:
        while True:
            # wait to accept a connection - blocking call
            conn, addr = s.accept()
            conn.settimeout(0.01)  # 10 ms
            print("Connection accepted")

            while True:
                try:
                    data = conn.recv(256)
                    if not data:
                        break
                    uart.write(data)
                except OSError:
                    pass

                data = uart.read()
                if data:
                    conn.send(data)

            conn.close()
            print("Connection closed")
    except BaseException:
        s.close()
        print("Terminating")


def setWakeCondition():
    '''Set wake conditions. Currently:
- microcontroller is woken up from deep sleep when pin 4 is high.'''

    if machine.wake_reason() == machine.PIN_WAKE:
        print("Woken up")
    else:
        print("Hello, world!")

    wake_pin = machine.Pin(4)
    wake_pin.init()

    wake_pin.irq(trigger=machine.Pin.WAKE_HIGH, wake=machine.DEEPSLEEP)


def main():
    setAccessPoint()
    setWakeCondition()
    pipeCommunication()

import machine


def connect():
    import network
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect('Sitecom1250C2_basic', 'orokg9mm')
        while not sta_if.isconnected():
            pass
    print('network config:', sta_if.ifconfig())


def accessPoint():
    import network
    ap_if = network.WLAN(network.AP_IF)
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(False)
    ap_if.active(True)


def pipeCommunication():
    import usocket as socket
    import uselect as select

    uart = machine.UART(1, baudrate=9600, rx=16, tx=17, timeout=10)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', '8888'))
    s.listen(1)

    while True:
        # wait to accept a connection - blocking call
        conn, addr = s.accept()
        conn.settimeout(0.01)  # 10 ms
        print("connection accepted!")
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
        print("connection closed")


def main():
    accessPoint()
    if machine.wake_reason() == machine.PIN_WAKE:
        print("woken up!")
    else:
        print("Hello, world!")
    p1 = machine.Pin(4)
    p1.init()

    p1.irq(trigger=machine.Pin.WAKE_HIGH, wake=machine.DEEPSLEEP)

    print("Commencing pipeline")
    pipeCommunication()

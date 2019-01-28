# PyPlug ESP32 Firmware

This firmware is meant to be flashed on PyPlug's ESP32. The role of the ESP is to poll values from the PIC MCU, and to provide an higher-level 'hackable' software interface for the device.

The firmware is built over MicroPython (version 1.9.4-773). MicropPython is
> a lean and efficient implementation of the Python 3 programming language that includes a small subset of the Python standard library and is optimised to run on microcontrollers and in constrained environments.

You can find more informations on the [official MicroPython website](http://micropython.org/).

This repository contains an example of a firmware capable of exploiting many of the capabilities offered by this device. However, there are a lot more different ideas and firmwares which can be implemented, for example [a bot for controlling PyPlug using Telegram](https://gist.github.com/aleeraser/41ae90eaaca5ce0b74cfc3dc317d497a).

Also bear in mind that this firmware was developed `ad-hoc` for the [PyPlug mobile application](https://github.com/aleeraser/PyPlugApp).

## Commands

The firmware expects to find a `cfg.py` file containing:

- `device_name`: device display name
- `ssid`: SSID name
- `psw`: SSID password

formatted as python variables. If a `device name` is not found, a default one will e used. On the other hand, if `ssid` and/or `psw` are missing or invalid, the ESP will not be able to connect and it will fall back to its AP facility.

The execution is subdivided in two different threads, one listening for TCP socket connections, and the other listening for UDP (broadcast) messages. The latter is used as a service discovery entry point, while the former handles the communication between all the clients (PyPlug apps, netcat, ...).

The custom `ATCOMMANDS` implemented in the PIC MCU have been extended in order to implement ESP-specific features, and also for a matter of convenience: return values, if present, are represented as comma-separated strings. In particular, the following commands have been added:

- `ATREBOOT`: reboots the ESP32
- `ATREPL`: enters REPL mode (e.g. terminates `main.py` execution). This is particularly useful in order to enable the ESP to be reprogrammed via a REPL prompt (e.g. Serial, WebREPL). More info [here](https://docs.micropython.org/en/latest/esp8266/tutorial/repl.html).
- `ATTIMER`: enables to get, set or delete the current timer. The syntax corresponds the `ATTIMER` command, followed by:
  - `GET`: get current timer informations in the form of `seconds_remaining, command`
  - `DEL`: delete the current timer
  - `SET,seconds,command`, where command must be one between `ATON` or `ATOFF`: set a timer
- `ATNET`: enables to set or get the ssid and password of the wireless network memorized by the ESP. The syntax corresponds the `ATTIMER` command, followed by:
  - `GET`: get current network informations in the form of `ssid, password`
  - `SET,ssid,password`: set wireless network access informations
- `ATNAME`: get or set the device name. The syntax corresponds the `ATNAME` command, followed by:
  - `GET`: get current device name
  - `SET,name`: set device name
- `ATALL`: return relevant status informations. In particular:
  - state (`ATSTATE`)
  - current (`ATCURRENT`)
  - power (`ATPOWER`)
  - remaining timer seconds (-1 if no timer is set)
  - timer command (None if no timer is set)
  - network ssid (None if not present)
  - network password (None if not present)
  - device name

Every command must be terminated with the newline (`\n`, or ASCII code 10) character. Since UART communications are non blocking, in order to be able to determine when a response from the PIC has been fully received, the ESP waits in turn for a `\n` terminating character.

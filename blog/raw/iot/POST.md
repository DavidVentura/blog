# Idea
I bought a few sonoff basics and wanted to set up some sensors and triggers around the house, with some restrictions:

* If a sensor or switch replaces something existing, then there should be always a fallback to that functionality even if there's no connectivity.
* Code should be fully open
* There should be no complex infrastructure to support this

# Evaluating the board

I wanted a cheap board that included a mains transformer as both using phone chargers (NodeMCU) or building your own [1](images/esp8266psu.jpg) ends up being more expensive, cumbersome and prone to failures.
Winner: Sonoff basic.

<table>
    <tr> <th>GPIO</th> <th>NAME</th> <th>IN/OUT</th> <th>NOTES</th> </tr>
    <tr> <td>0</td>  <td>button</td> <td>IN   </td> <td></td> </tr>
    <tr> <td>1</td>  <td>TX</td>     <td>INOUT</td> <td>outputs garbage on boot</td> </tr>
    <tr> <td>3</td>  <td>RX</td>     <td>INOUT</td> <td></td> </tr>
    <tr> <td>12</td> <td>relay</td>  <td>  OUT</td> <td>powered from mains</td> </tr>
    <tr> <td>13</td> <td>led</td>    <td>  OUT</td> <td>inverted high/low</td> </tr>
    <tr> <td>14</td> <td>GPIO</td>   <td>INOUT</td> <td></td> </tr>
</table>

Also note that if you fuck up the TX/RX pins you won't be able to flash the Sonoff again.

I ended up choosing to go for independent modules written in MicroPython, where the communication bus is MQTT.

To get MicroPython on the board you should solder the 4 UART pins on the board and flash the firmware.

# Flashing


I was running (as recommended [here](https://docs.micropython.org/en/latest/esp8266/esp8266/tutorial/intro.html))

```
esptool.py --port /dev/ttyUSB0 erase_flash
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 esp8266-20170108-v1.8.7.bin
```

The first issue I had was that the TX/RX pair is reversed on my revision of the board, but that's a simple cable switch.
The second issue is that my firmware flashes kept failing, and as found [here](https://forum.micropython.org/viewtopic.php?t=4385), the manufacturer of my board was `5e` so I modified the flash command slightly to

```
esptool.py --port /dev/ttyUSB0 erase_flash
esptool.py --port /dev/ttyUSB0 write_flash -fs 1MB -fm dout 0x0 esp8266-20180511-v1.9.4.bin
```

# Getting a REPL

While you can use `screen`, `minicom`, `picocom` or other software for serial communication, you also will (most likely) want to push files into the [VFS](https://docs.micropython.org/en/latest/esp8266/esp8266/tutorial/filesystem.html).

What I used for both getting a REPL and pushing files is [mpfshell](https://github.com/wendlers/mpfshell), which sometimes sadly fails, but >90% of the time works great.

My `rapid iterations` are done by running

```
mpfshell ttyUSB0 -c "put main.py; repl; exit"
```

and pressing `Ctrl-D` immediately which soft-reboots the esp8266. I'll see my code run, play around in the REPL and iterate. To exit mpfshell you need to press `Ctrl-Alt-]`.



# Writing some code

With the way I set up the common functions, you can have something working in ~20 lines of code (omitting imports) 

DHT22 -> MQTT
```python
CLIENT_ID = 'TEMPSENSOR'
TEMPTOPIC = b"TEMP/%s" % CLIENT_ID
HUMTOPIC = b"HUM/%s" % CLIENT_ID

led = Pin(13, Pin.OUT)
dht = dht.DHT22(Pin(14))

@common.debounce(60000)
def read_dht():
    dht.measure()
    common.mqtt.publish(TEMPTOPIC, "%.2f" % dht.temperature())
    common.mqtt.publish(HUMTOPIC, "%.2f" % dht.humidity())

def main():
    setup_fns = [ lambda: led(1) # Turn off LED, it is inverted
                ]
    common.loop(CLIENT_ID, setup_fn=setup_fns, loop_fn=[read_dht], callback=sub_cb, subtopic=SUBTOPIC)

main()
```

Pub/sub + button for relay
```python
CLIENT_ID = 'NIGHTLAMP'
SUBTOPIC = b"%s/set" % CLIENT_ID
PUBTOPIC = b"%s/state" % CLIENT_ID

button = Pin(0, Pin.IN)
led = Pin(13, Pin.OUT)
relay = Pin(12, Pin.OUT)

def set_pin(pin, state):
    pin(state)
    common.mqtt.publish(PUBTOPIC, str(pin()))

def sub_cb(topic, msg):
    if msg == b'1':
        set_pin(relay, True)
    elif msg == b'0':
        set_pin(relay, False)
    else:
        set_pin(relay, not relay())

@common.debounce(250)
def handle_button(pin):
    set_pin(relay, not relay())

def main():
    setup_fns = [ lambda: button.irq(handler=handle_button, trigger=Pin.IRQ_RISING),
                  lambda: led(1) # Turn off LED, it is inverted
                ]
    common.loop(CLIENT_ID, setup_fn=setup_fns, loop_fn=[], callback=sub_cb, subtopic=SUBTOPIC)

main()
```

The mqtt lib is [umqtt.simple](https://github.com/micropython/micropython-lib/tree/master/umqtt.simple) which is an official lib.
You can find the common lib on [github](https://github.com/DavidVentura/iot_home).

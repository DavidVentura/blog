


## Capturing packets from an android device on linux
To capture bluetooth on android you have to enable `HCI snoop log`, you can do
so by going to `Preferences -> System -> Developer Options -> Enable Bluetooth HCI Snoop log`
and then turning bluetooth off and on again.

Now that you can capture bluetooth you have two options:

1. Do nothing (just play around with the bluetooth app controls) and after a while stop bluetooth, then fetch the dump file located at `/data/misc/bluetooth/logs/btsnoop_hci.log` (requires root).
2. Use `androiddump` (from the package `wireshark-common`) to do live capture of the bluetooth packets.


I'll use `androiddump` as inspecting what you do live is a lot easier for me, to
do so you have to find your bluetooth interface:

```
$ androiddump --extcap-interfaces
...
interface {value=android-bluetooth-btsnoop-net-fc6c2719}{display=Android Bluetooth Btsnoop Net Poco_F1 fc6c2719}
```

If you don't see the `btsnoop` interface here most likely you didn't enable the
HCI Snoop log and restarted bluetooth afterwards.

Then set up a fifo, have wireshark look at it and start dumping the packets to it

```
$ mkfifo /tmp/fifo
$ wireshark -k -i /tmp/fifo &
$ androiddump --extcap-interface=android-bluetooth-btsnoop-net-fc6c2719 --fifo=/tmp/fifo --capture
```

In wireshark you want to filter by `btspp`. 

![An example of a btspp packet](/images/reverse-engineering-bose-qc35/wireshark-device-status.png)


## Figuring out the protocol

To figure out the protocol what I'd normally do is be patient and click all the
buttons on the UI, recording what each of them maps to. In this case, most of
that proved to be unnecessary as `Denton-L` had already done most of it in this
project (which I've used in the past): [based-connect](https://github.com/Denton-L/based-connect/).

After compiling a list of all the sent and received messages I made the
following conclusions about the protocol:


**There is no checksum**:

Taking as an example the `NOISE_LEVEL` messages, a sigle byte represents the
noise cancelling level, but no other byte changes, so this means no
checksumming is done.

```
NOISE_LEVEL_LOW( (0x01, 0x06, 0x02, 0x01, 0x03)),
NOISE_LEVEL_HIGH((0x01, 0x06, 0x02, 0x01, 0x01)),
NOISE_LEVEL_OFF( (0x01, 0x06, 0x02, 0x01, 0x00)),
```

**Messages consist of a 3 byte header and 1 byte indicating how many bytes of
data will follow**:

Types of messages **sent** from the device:
```kotlin
CONNECT(            (0x00, 0x01, 0x01, 0x00)),
GET_DEVICE_STATUS(  (0x01, 0x01, 0x05, 0x00)),
GET_BATTERY_LEVEL(  (0x02, 0x02, 0x01, 0x00)),
NOISE_LEVEL_LOW(    (0x01, 0x06, 0x02, 0x01, NoiseLevels.LOW.level)),
NOISE_LEVEL_HIGH(   (0x01, 0x06, 0x02, 0x01, NoiseLevels.HIGH.level)),
NOISE_LEVEL_OFF(    (0x01, 0x06, 0x02, 0x01, NoiseLevels.OFF.level)),
AUTO_OFF_NEVER(     (0x01, 0x04, 0x02, 0x01, AutoOffTimeout.NEVER.timeout)),
AUTO_OFF_20(        (0x01, 0x04, 0x02, 0x01, AutoOffTimeout._20.timeout)),
AUTO_OFF_60(        (0x01, 0x04, 0x02, 0x01, AutoOffTimeout._60.timeout)),
AUTO_OFF_180(       (0x01, 0x04, 0x02, 0x01, AutoOffTimeout._180.timeout)),
BTN_MODE_ALEXA(     (0x01, 0x09, 0x02, 0x03, 0x10, 0x04, 0x01)),
BTN_MODE_NC(        (0x01, 0x09, 0x02, 0x03, 0x10, 0x04, 0x02)),
```

Types of messages **received** in the device:
```kotlin
CONNECT(            (0x00, 0x01, 0x03, 0x05)),
ACK_1(              (0x01, 0x01, 0x07, 0x00)),
ACK_2(              (0x01, 0x01, 0x06, 0x00)),
NAME(               (0x01, 0x02, 0x03, ANY, 0x00)),
AUTO_OFF(           (0x01, 0x04, 0x03, 0x01, ANY)),
BATTERY_LEVEL(      (0x02, 0x02, 0x03, 0x01, ANY)),
NOISE_LEVEL(        (0x01, 0x06, 0x03, 0x02, ANY,  0x0b)),
BTN_ACTION(         (0x01, 0x09, 0x03, 0x04, 0x10, 0x04, ANY, 0x07)),
LANG(               (0x01, 0x03, 0x03, 0x05, ANY,  0x00, ANY, ANY, 0xde)),
UNKNOWN(            (0x7E, 0x7E)) // 0x7E is an invalid byte to receive
                                  // this value is only used to mark that we could not parse anything
```
It's very clear in this list that the 4th byte indicates how many bytes of data
are remaining, and there's an even more clear example -- when receiving the
device's name (which is variable by nature) with the 4th byte specifying a
variable number of bytes that follow with data.

Something to note is that the messages starting with the byte `0x0` don't seem
to conform to this rule.

**Any amount of messages can be present in a single packet**

In particular, when requesting the device status, the reply includes 6 messages
in a single packet.

## Parsing a message 

If we take the bytes from the first image:
```
0000   01 01 07 00 01 02 03 0d 00 42 6f 73 65 20 51 43   .........Bose QC
0010   33 35 20 49 49 01 03 03 05 81 00 04 cf de         35 II.......ÏÞ
```

and parse with the protocol we have so far, we can see that this packet represents:

1. ACK\_1
2. NAME
3. LANG
4. AUTO\_OFF
5. NOISE\_LEVEL
6. BTN\_ACTION


## Results

With the protocol more or less understood, I wrote a small android
application to control the headphones. You can find it [here](https://github.com/DavidVentura/Bose_QC35_Android), keep in mind that it's of alpha quality, but it works somewhat fine.

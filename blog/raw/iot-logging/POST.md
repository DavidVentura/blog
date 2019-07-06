I am trying to debug why my IOT devices don't always recover from a DNS/DHCP failure &ndash; it is quite hard as they simply get stuck, not doing anything until rebooted.   
I'll go over what I am currently doing to try and shed some light on the possible causes.

# Preparing for disaster

Only one of the devices I have currently installed is accessible from the serial debug port &ndash; the rest are carefully hidden inside walls, and while I was confident that
my changes to the firmware would work (as they work on a 'blank' device) I wanted to be doubly sure and avoid the pain of re-wiring everything.

The most accessible ESP8266 is connected to my Odroid N2 via USB, but this Odroid is running CoreElec, a very stripped down linux distribution for media which has no package manager.


Usually the tool I choose for serial debugging is `minicom` so I set on to cross-compile it from my x86\_64 box so that it'd run on the aarch64 Odroid.

## Compiling minicom


```bash
minicom $ ./configure --host=aarch64 --build=x86_64 CC='arm-linux-gnueabihf-gcc-8'
minicom $ make -j8
ld: minicom/src/window.c:196: undefined reference to `tputs'
ld: minicom/src/window.c:1954: undefined reference to `tgetstr'
ld: minicom/src/window.c:1967: undefined reference to `tgetnum'
```

The complaints about `tputs` point to missing `ncurses` references, so off to build ncurses.

```bash
ncurses $ ./configure --host=aarch64 --build=x86_64 CC='arm-linux-gnueabihf-gcc-8'
ncurses $ make -j8
```

Linking the newly-built ncurses

```bash
minicom $ ./configure --host=aarch64 --build=x86_64 CC='arm-linux-gnueabihf-gcc-8 -L~/git/ncurses/lib'
minicom $ make -j8
minicom $ file src/minicom
src/minicom: ELF 32-bit LSB shared object, ARM, EABI5 version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-armhf.so.3, BuildID[sha1]=4a85f2b5e2e7d0a48214743265505cc23b461a7e, for GNU/Linux 3.2.0, with debug_info, not stripped
```

Copy the binary over aaand:

```bash
root@odroid $  ./minicom -D /dev/ttyUSB0
No termcap database present!
```

Checking `/etc/terminfo/README` in my debian machine has all the info I need

```
This directory is for system-local terminfo descriptions. By default,
ncurses will search ${HOME}/.terminfo first, then /etc/terminfo (this
directory), then /lib/terminfo, and last not least /usr/share/terminfo.
```

so let's retry after copying over `/usr/share/terminfo` to `~/.terminfo`

```bash
root@odroid $ ./minicom -D /dev/ttyUSB0
No termcap entry for xterm
```

Let's just override that with something present in `~/.terminfo`:
```bash
root@odroid $ ./minicom -D /dev/ttyUSB0 -t rxvt-256color
Welcome to minicom 2.6.2

OPTIONS: I18n
Compiled on Jul  6 2019, 10:27:35.
Port /dev/ttyUSB0, 15:39:48

Press CTRL-A Z for help on special keys
^D
{r�#5 ets_task(40100130, 3, 3fff83ec, 4)
LOCAL-Connecting to Wi-Fi... SSID
LOCAL-Waiting wifi...
Connected to SSID!
Subscribing to b'RFPOWER/set/#'
Subscribing to b'HDMI/set/#'
```

We have an emergency avenue into this device!

# Logging

By the very nature of these devices, it is hard to get information out of them. They have no screens, and although they do have a single LED on which they could show
some pattern, they are usually *inside* the walls.  

Adding to these charateristics, there's hardly any guarantee on **when** we'll see a failure &ndash; and given there's no local storage, the best that can be done is to *try* and output something useful on the network.  

I implemented this with a very basic UDP server and a pipe-delimited message format `NAME|CONTENTS`.  
After updating the `common.py` and making some small tweaks to the firmware on all devices, the data received on the logging server looks something like:

During normal operation:  

```bash
$ ./logserver.py
2019-07-06 12:03:29,101 - INFO - [RFPOWER]: Topic: HDMI/set
2019-07-06 12:03:29,102 - INFO - [RFPOWER]: Msg: 1
2019-07-06 12:03:58,672 - INFO - [RFPOWER]: Topic: RFPOWER/set/2
2019-07-06 12:03:58,676 - INFO - [RFPOWER]: Msg: 0
2019-07-06 12:03:59,109 - INFO - [RFPOWER]: Publish 0 to b'RFPOWER/state/2'
```

For OTA:  

```bash
$ ./logserver.py
2019-07-06 12:00:02,062 - [RFPOWER]: Receiving OTA update..
2019-07-06 12:00:02,074 - [RFPOWER]: Target IP: 192.168.2.189, Target Port: 1233, Local filename: common.py, hash: 3471ff7786fb04d064e555e6588ca3d74f6b111a
2019-07-06 12:00:02,518 - [RFPOWER]: renaming tmp to common.py
2019-07-06 12:00:02,719 - [RFPOWER]: restarting
2019-07-06 12:00:07,491 - [RFPOWER]: Connected to SSID!
2019-07-06 12:00:07,844 - [RFPOWER]: Subscribing to b'RFPOWER/set/#'
2019-07-06 12:00:07,970 - [RFPOWER]: Subscribing to b'HDMI/set/#'
```

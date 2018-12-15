# Idea
Most nights I read from my Kindle until fall asleep, leaving my night light on.. after a few hours I usually wake up, annoyed at the light and turn it off, but some nights I cannot fall back asleep..

So, I thought why not have the light turn itself off when I fall asleep? Given that I can already turn it on/off via my home automation scripts, it should not be too difficult to detect somehow that my kindle went off.

# First attempt: Network detection
I started by trying to detect the activity from the kindle on my own wifi, but mucking with openwrt to detect a device's activity was neither straightforward nor (once it was working) accurate / fast enough.

# Second attempt: Tailing logs in Bash
As I had already jailbroken my kindle I thought about doing something on the device, but the userland is quite limited..  
I started exploring the device and I found that I could somewhat reliably detect the screen changing state by `grep`ping  `/var/log/messages`

```
[root@kindle root]# grep SCREEN /var/log/messages
181215:164756 powerd[1096]: I def:statech:prev=ACTIVE, next=SCREEN SAVER:State change: ACTIVE -> SCREEN SAVER
181215:164856 powerd[1096]: I def:statech:prev=SCREEN SAVER, next=READY TO SUSPEND:State change: SCREEN SAVER -> READY TO SUSPEND
```

My initial working attempt looked something like

```
grep SCREEN /var/log/messages | while read -r line; do
    echo $line | nc -u 192.168.2.10 8888
done
```

and I simply ran it in the background from an ssh session.

This attempt was a bit crude; as it did not reliably manage to send "SCREEN ON" messages, the wifi shuts off while the system is sleeping and this script will try to deliver the message before the wifi connection is up.

I did try to periodically check whether the wifi was down and wait but it got quite cumbersome to deal with in bash, which led to..

# Third attempt: Python

I thought, if this is just an ARM linux distro, could I not just `scp` over some python binaries and be done with it?

```
[root@kindle root]# file /mnt/us/python/bin/python2.7
python2.7: ELF 32-bit LSB executable, ARM, EABI5 version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux.so.3, for GNU/Linux 2.6.31, stripped
```

Well, yes! I originally got them from (somewhere?) in the Debian repos, but you can also find them [here](https://www.mobileread.com/forums/showthread.php?t=195474).

Now that I had a handy python binary in my kindle I could more comfortably manage the state required to send messages when appropiate, so I essentially ported my bash script to python, but I did not like the (working) result.

I decided to dig a bit deeper to avoid the fragile parsing of `/var/log/messages` and I found `lipc-wait-event` (you can find a detailed list of events [here](https://wiki.mobileread.com/wiki/Lipc)).

``` bash
[root@kindle root]# lipc-wait-event -mt "com.lab126.powerd" "*"
[11:28:12.711741] goingToScreenSaver 2
[11:28:17.554321] t1TimerReset
[11:28:17.580866] outOfScreenSaver 1
[11:28:24.081409] goingToScreenSaver 2
[11:28:27.298605] outOfScreenSaver 1
[11:29:27.421299] charging
[11:30:20.656191] battLevelChanged 21
```

```bash
[root@kindle root]# lipc-wait-event -m com.lab126.wifid "*"
scanning
scanComplete
cmDisconnected
cmStateChange "NA"
signalStrength "0/5"
cmStateChange "READY"
cmIntfNotAvailable
cmStateChange "NA"
cmStateChange "PENDING"
scanning
scanComplete
cmConnected
cmStateChange "CONNECTED"
signalStrength "4/5"
scanning
cmConnected
cmConnected
scanComplete
```

I could now subscribe to these two event sources individually and get reliably notified when something _interesting_ happened.

My final script:

```python
#!/usr/bin/env python2                                                                                                                                                                                                                                                                                                       
import subprocess                                                                                                                                                                                                                                                                                                            
import socket                                                                                                                                                                                                                                                                                                                
import time                                                                                                                                                                                                                                                                                                                  
from threading import Thread                                                                                                                                                                                                                                                                                                 
                                                                                                                                                                                                                                                                                                                             
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)                                                                                                                                                                                                                                                             
client_socket.settimeout(1.0)                                                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                                                             
def udp_send(key, value):                                                                                                                                                                                                                                                                                                    
    try:                                                                                                                                                                                                                                                                                                                     
        print("Sending", key, value)                                                                                                                                                                                                                                                                                         
        message = b'%s|%s' % (key, value)                                                                                                                                                                                                                                                                                    
        addr = ("192.168.2.1", 12000)                                                                                                                                                                                                                                                                                        
        client_socket.sendto(message, addr)
    except Exception as e:
        print(e)                                                                                                                                                                                                                                                                                                             
                                                                                                                                                                                                                                                                                                                             
def pub_event(source, events):                                                                                                                                                                                                                                                                                               
    comm = ['lipc-wait-event', '-m', source]                                                                                                                                                                                                                                                                                 
    comm.extend(events)                                                                                                                                                                                                                                                                                                      
    s = subprocess.Popen(comm, stdout=subprocess.PIPE)                                                                                                                                                                                                                                                                       
    for line in iter(s.stdout.readline, ""):                                                                                                                                                                                                                                                                                 
        line = line.strip()                                                                                                                                                                                                                                                                                                  
        print(source, line)                                                                                                                                                                                                                                                                                                  
        if 'goingToScreenSaver' in line:                                                                                                                                                                                                                                                                                     
            udp_send('screen', 'off')                                                                                                                                                                                                                                                                                        
        if 'outOfScreenSaver' in line:                                                                                                                                                                                                                                                                                       
            udp_send('screen', 'on')                                                                                                                                                                                                                                                                                         
        if 'battLevelChanged' in line:                                                                                                                                                                                                                                                                                       
            udp_send('bat', line.split(" ")[1])                                                                                                                                                                                                                                                                              
        if 'cmConnected' in line:                                                                                                                                                                                                                                                                                            
            udp_send('wifi', 'on')                                                                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                                                             
udp_send('init', 'init')                                                                                                                                                                                                                                                                                                     
power = Thread(target=pub_event, args=("com.lab126.powerd", ["*"]))                                                                                                                                                                                                                                                          
wifi = Thread(target=pub_event, args=("com.lab126.wifid", ["cmConnected"]))                                                                                                                                                                                                                                                  
power.start()                                                                                                                                                                                                                                                                                                                
wifi.start()                                                                                                                                                                                                                                                                                                                 
                                                                                                                                                                                                                                                                                                                             
power.join()                                                                                                                                                                                                                                                                                                                 
wifi.join()     
```

# Auto startup

There are quite some ways to add "services" to the kindle, but I opted for an upstart entry: `/etc/upstart/automation.conf`

```
# Script run after all filesystems have loaded

start on started filesystems_userstore
stop on stopping filesystems

export LANG LC_ALL

pre-start script
  python /mnt/us/test.py &
end script
```

# Debugging

Doing remote work on the kindle is quite annyoing as it will try to limit its bandwidth and shut down the wifi at any opportunity; setting the wlan power setting to `maxperf` solves the issue

```bash
# cat /mnt/us/fast_wifi.sh
wmiconfig -i wlan0 --power maxperf
```

Don't forget to set it back to `rec` later, or your battery will drain quite quickly.



# Result

<video controls="true"><source src="videos/kindle_light.mp4"></video>


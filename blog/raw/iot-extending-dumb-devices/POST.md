---
title: Extending the capabilities of dumb devices
date: 2019-07-06
tags: iot, python, kindle
description: Hooking non-smart devices into the house automation framework
---
As with my [kindle hack](/integrating-a-kindle-into-house-automation.html), I wanted to extend a 'dumb' device, my HDMI input selector.

The input selector originally looked like this:

![](images/hdmi_switcher_example.jpg)

It simply switches between available inputs whenever the button is toggled.  
Believe it or not, standing up, walking to the TV and pressing this button is incredibly faster than using the crappy remote to navigate the crappy interface on our tv.  
And while it **is** faster, it is also not as easy as clicking some button remotely, and so the remote-button-presser was born!

![](images/hdmi_switcher.jpg)

While the button-pressing is extremely simple to implement based on my previous iot ['framework'](https://github.com/DavidVentura/iot_home/blob/master/firmware/rf433.py) &ndash; the hardest part by far was a way to detect
which input is selected.. at least without getting the device out from the wall and using the LEDs as inputs for the ESP8266.

## Getting input 

There are only 2 devices connected and one of them can output whether or not it has an HDMI cable connected by reading `/sys/devices/virtual/amhdmitx/amhdmitx0/hdmi/cable.0/state`.  
As this device (Odroid) has a very limited linux runtime, I setteld on sending UDP messages (same as the [kindle](/integrating-a-kindle-into-house-automation.html)) to a local server that converts them to MQTT.

## Results

<video controls="true"><source src="videos/tv_switching.mp4"></video>


## Why not CEC?

Couldn't get it to work with our devices.

# Curtains/Blinds automation

In a similar vein, I've also wired 2 relays to my electric curtains controls
with wifi integration. The software is the same as before and you can see it
[here](https://github.com/DavidVentura/iot_home/blob/master/firmware/curtains/main.py)
-- it simply holds the correct relay closed for the specified amount of time.


## Results
<video controls="true"><source src="videos/curtains.mp4"></video>

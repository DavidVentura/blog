---
title: Revamping an old tv as a gift
date: 2019-10-14
tags: python
description: Putting a raspberry pi in a 60's CRT for a gift
---
This entry is a summary of what I built for my dad's 50th birthday, in 2017.

The plan was to get a vintage TV to play some shows from the 70s-80s, and
operation should be seamless.

The sacrificial lamb, found in the flea market:

![](/images/old-tv/front.jpg)
<center><small>The tiny sticker says "It works"</small></center>

![](/images/old-tv/back.jpg)


With the lid off

![](/images/old-tv/insides.jpg)

The tuner
![](/images/old-tv/sintonizador.jpg)


---

The attack plan:

# Getting the raspberry pi to output video to the TV

Because the raspberry only outputs composite video, I needed a 'composite RF
modulator' that'd convert the signal to a format that this TV can display.

These modulators output different channels at different frequencies.
![](/images/old-tv/rca-rf.jpg)

These frequencies are what you 'tune' to by rotating the tuner's knob ([learn more about tuners here](https://hackaday.com/2016/07/11/not-quite-101-uses-for-an-analog-uhf-tv-tuner/)).
I left the tv tuner in a fixed channel, the same as what the modulator outputs.

*Let there be video!*

![](/images/old-tv/firstboot.jpg)

# Software-based channels

With the Pi's output being displayed on the TV the next step was to get back the
functionality of being able to rotate the knob to change channels.  
I did this with software-based channels, controlled by a multi-polar rotary switch.

![](/images/old-tv/selector-side.jpg)

Switch connected to GPIO 
![](/images/old-tv/switch-gpio.jpg)


# Powering the pi and modulator inside the TV

The raspberry pi needs a 5v power source, and the RF modulator needed 9v.  
I found a 12v rail and mounted an LM7809 and LM7805 to obtain the needed
voltages inside the TV.

LM7809 and LM7805 placed using part of the TV as a heatsink
![](/images/old-tv/7805.jpg)

---


# Software

Initially, the idea was to have a large set of shows/chapters (and
advertisements) per channel, and pick from them randomly.

I had just recently started to get familiar with `gstreamer` and could not get
my player to continuously play seamlessly -- either changing pads or containers
or something else would always make it get stuck after a while.

I opted to go with a massive hack: each channel is a single 8-hours long video,
with the advertisements baked in.

On poweroff, the timestamp of the nearest keyframe is saved and on power-on,
playback resumes from there.

When a video reaches the end of playback, it will start again from the
beginning.

The code can be found [here](https://github.com/DavidVentura/old-tv), but be
warned, it is very bad.


---

First time I got it working -- the black spots are an artifact my phone's
recording..

<video controls="true"><source src="/videos/old-tv/tv-first-working-day.mp4"></video>

Final version
<video controls="true"><source src="/videos/old-tv/tv-finished.mp4"></video>

# Extra

I also made a fake parcel-tracking website that'd display the status of the package.
![](/images/old-tv/tracking-1.png)


![](/images/old-tv/tracking-2.png)

# Inspiration


[This](https://hackaday.com/2017/02/23/bring-saturday-mornings-back-to-life-with-this-cartoon-server/) [guy](https://twitter.com/FozzTexx/status/825358304515747840) made me think about this in the first place.
Our approaches are quite different, as I wanted to have the TV be 'stand alone'.

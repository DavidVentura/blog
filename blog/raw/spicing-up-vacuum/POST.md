---
title: Spicing up a robot vacuum
date: 2023-09-18 
tags: vacuum, rust, short
description: Playing sound on a robot vacuum
---

Some time ago, I bought a [Dreame Z10 Pro](https://www.dreametech.com/products/dreame-z10-pro) robot, which I immediately un-clouded by [installing](/images/vacuum/day1.jpg) [Valetudo](https://github.com/Hypfer/Valetudo).

A friend challenged me to make this thing play [Ride of the Valkyries](https://www.youtube.com/watch?v=N0EPcjnYXNU) as it vacuums, so I immediately started hacking at it.

These robots pack a surprisingly large amount of computing power; 512MB of ram and a 4-core, 1.4GHz, Cortex A53 processor (aarch64), running a 4.9 kernel.

The first thing I did, was to validate whether this was possible at all with a super high-tech approach, pressing this button:
<center>![](/images/vacuum/test_volume.png)</center>

while looking at the output of `htop`, which, for a brief second, displayed:

```bash
/bin/sh /ava/script/mediad_script.sh /audio/EN/7
```

The script, like the rest of the firmware image, is pretty low quality. I dug through a few levels of `source`s and "manually" evaluated all the conditions, the code that executes is just 4 lines:

```bash
SET_AMIXER_CMD="amixer cset numid=6"
MAX_MEDIA=31
${SET_AMIXER_CMD} ${MAX_MEDIA}
ogg123 ${1}.ogg
```

Oddly, I failed to copy the file, as the ssh server (dropbear) does not support the `sftp` protocol
```bash
$ scp root@vacuuminator.labs:/audio/EN/7.ogg .
sh: /usr/libexec/sftp-server: not found
scp: Connection closed
```

However... it still has `cat`
```bash
$ ssh root@vacuuminator.labs "cat /audio/EN/7.ogg" > 7.ogg
```
🧠

With the `7.ogg` on hand, I checked its format: it is a 16kHz, single-channel file, which is (apparently) all that the audio hardware supports.

I converted my track to match the supported format:

```bash
$ ffmpeg -i valkyries.m4a -ac 1 -ar 16000 valkyries.ogg
```

I then [built](https://github.com/DavidVentura/GalacticVacuum) a very simple OGG player in Rust, which lets me start and sto the music track dynamically, and this is the result:

<video controls="true"><source src="/videos/valkyries.mp4"></video>

---
title: A month writing embedded projects for the ESP32
date: 2024-03-15
tags: rust, esp32, embedded
slug: esp32-rust-projects
incomplete: yes
description: 
---

Over the last I worked on some projects that I've had on my backlog for a while

## Pixelated fireplace

I wanted to build a pixelated fire place, so I bought 5 arrays of WS2812B in an 8x32 configuration.

I assembled them on a piece of cardboard, with crudely made holes for the cables:
![](/images/esp32-rust-projects/backing-tape.jpg)

<video src="/videos/esp32-rust-projects/fire-first-test.mp4" controls loop></video>

Hackerspace, lasercutter, postscript file: https://github.com/DavidVentura/matrix-fire/blob/master/parts/baffles.ps
fuckery with scale and polyaslines

<video src="/videos/esp32-rust-projects/laser-cutter-test.mp4" controls></video>
![](/images/esp32-rust-projects/laser-cutter-done.jpg)

![](/images/esp32-rust-projects/baffles-done.jpg)

After a test, it works fine
![](/images/esp32-rust-projects/first-demo.jpg)

When enabling wifi, it no longer works fine

<video src="/videos/esp32-rust-projects/wifi-interrupts.mp4" loop controls></video>

interrupts, etc.

with fixed interrupts

<video src="/videos/esp32-rust-projects/working-demo.mp4" controls></video>

## Stratum 1 NTP server

pretty easy. signal on neoblox6m ass

## Rain radar
TODO


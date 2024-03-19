---
title: Measuring keyboard to display latency
date: 2022-07-09
tags: rp2040, sdl, latency
description: 
---

I've got fed up with some latency I've been experiencing when using the work-issued VPN (remote desktop over IP), and wanted to 
get measurements, to see if the latency perceived is real.

The approach is as basic and end-to-end as I could think of: emulate a USB keyboard pressing a button and measure the light levels changing on screen. 

<center>
  <video controls="true">
    <source src="/videos/delay-measure.webm" type="video/webm">
  </video>
</center>


## Software on the target to measure

Wrote a very basic [SDL](https://www.libsdl.org/) program to flash the screen white while the spacebar is being held down, effectively it boils down to:

```c
if (key_pressed) {
    SDL_SetRenderDrawColor( gRenderer, 0xFF, 0xFF, 0xFF, 0xFF );
} else {
    SDL_SetRenderDrawColor( gRenderer, 0x00, 0x00, 0x00, 0x00 );
}
SDL_RenderClear(gRenderer);
SDL_RenderPresent(gRenderer);
```

which means "If the key is pressed, make the window white, otherwise make it black"


## Microcontroller software

Wrote a very basic Arduino sketch for its trivial-to-use USB HID support, which will take the mean result of 10 measurements after detecting a button press.

## Hardware

The light sensor is a basic LDR (light dependent resistor) which is not great, because these take a "significant" amount of time to settle to new values when their input changes. The typical latencies I've found online are ~8ms for a full transition (0% -> 100%)

Here's a very basic schematic:

![](/images/latency-schematic.png)

## Data


|Target|Measurement|Notes|
|------|-----------|-----|
|Linux 5.13, Dell P2418D|53ms|60Hz|
|Linux 5.13, Dell P2418D|36ms|60Hz, Enabled "Game Mode"|
|Linux 5.13, Dell+VPN|70-87ms|High variance|
|Linux 5.7, Thinkpad T430|51ms|60Hz, **no VSync**|
|14" M1 Macbook Pro|??|60Hz|


## Source

You can find the repo with the sources + schematic [here](https://github.com/DavidVentura/display-latency-measurement).

## References

- [Microsoft research into touch latency](https://www.youtube.com/watch?v=vOvQCPLkPt4)
- [Danluu's Keyboard latency analysis](https://danluu.com/keyboard-latency/)
- [Danluu's Input lag analysis](https://danluu.com/input-lag/)
- [Other end-to-end latency tester](https://thume.ca/2020/05/20/making-a-latency-tester/)
- [Latency testing end-to-end streaming solutions](https://thume.ca/2022/05/15/latency-testing-streaming/)

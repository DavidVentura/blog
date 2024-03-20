---
title: Exploring HUB75
date: 2024-03-20
tags: rust, esp32, embedded, rp2040
slug: exploring-hub75
incomplete: yes
description: 
---


The "HUB75" displays are quite interesting; they do not self-refresh, instead you have to constantly drive each LED to the desired value.

The LEDs themselves are only "1-bit" meaning that they can be on or off; the LEDs do not have support to set a specific color.

Interestingly, as the panels can refresh quite quickly, we can emulate color depth by varying the displayed color very quickly.

What we consider normal colors are usually represented in 3 channels, R, G and B. The color white is then represented as `#ffffff`:

<center>
	<img width="70%" src="/images/hub75/channels_exploded.svg"/>
</center>

FIXME

take the blue channel as an example

A bit plane of a digital discrete signal is a set of bits corresponding to a given bit position in each of the binary numbers representing the signal.
and if we take the same analogy, we can split a single _channel_ into different _bitplanes_ where a bitplane is 

<center>
	<img width="70%" src="/images/hub75/bitplane_exploded.svg"/>
</center>

Each bit-plane must be displayed for different lengths of time, otherwise the pattern `1100` and `0011` would be visible
as the same pattern.

To represent these bit-planes according to the color we'd expect, we can display each bit for twice as long as the previous
one and let our eyes do the "integration" of the image brightness.

In this case we'd be displaying the {^MSB|most significant bit} for 8 "periods", the next one for 4, then 2, then 1. 

Displaying brightness this way is called [binary coded modulation](http://www.batsocks.co.uk/readme/p_art_bcm.htm) or BCM.

Representing a complex color over time with bitplanes
<center>
	<img width="90%" src="/images/hub75/rgb_exploded.svg"/>
</center>

With all of these concepts in mind, we can display an image on the HUB75 displays.

## HUB75 protocol

The basic operation of the display:

- Select the current row index with the pins A, B, C, D
- Place the corresponding bit for the R1, G1 and B1 channels on the input, then shift it into the display by bringing `CLK` up and down.
- When you are done with the current row, bring `LATCH` up and down.

This lets you display an entire row of data. Repeat this with different values for A/B/C/D and you can shift in an entire bit plane.

In this case, we are shifting the 3 (R, G, B) bitplanes at once; on top of that, these displays usually populate two rows in parallel: [row index] and [row index + 16]; the second row is fed (R2, G2, B2).

## Math

For a given color depth D, we need to shift in 2<sup>D</sup> bitplanes, which constitute of R rows and C columns.

Taking my screen as an example (64 columns, 32 rows) and a 4 bit depth image, we would need to clock in 2<sup>4</sup> * 64 * 32 = 32768 pixels

Going to 5 bit depth doubles the pixels per frame to 65536 and 6 bit to 131072.

## Software implementation

As the protocol does not rely on a fixed clock, we can shift data in as fast/slow as we want, which leaves a lot of room
to [bit-bang](https://en.wikipedia.org/wiki/Bit_banging) the protocol

We can manipulate each pin individually, as an example:
```rust
if element.r1 > 0 {
	self.pins.r1().set_high()?;
} else {
	self.pins.r1().set_low()?;
}
if element.g1 > 0 {
	self.pins.g1().set_high()?;
} else {
	self.pins.g1().set_low()?;
}
// ...
self.pins._clk.set_low()?;
self.pins._clk.set_high()?;
```

[full code](https://github.com/DavidVentura/hub75-esp/blob/1d14ca3713b7ee1625bf3dc9b1c6a54c50e3b75c/src/hub75.rs)

5-bit image = 116ms

optimizing clock speed => `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`
5-bit image = 77ms; 50% speedup

optimizing build => `lto = true` in `Cargo.toml`
5-bit image = ~67ms; 15% speedup


The ESP32 supports setting/clearing the lower 32 pins (0..=31) in one memory write:
```rust
fn fast_pin_set(pins: u32) {
    unsafe { core::ptr::write_volatile(GPIO_OUT_W1TS_REG as *mut _, pins); }
}
fn fast_pin_clear(pins: u32) {
    unsafe { core::ptr::write_volatile(GPIO_OUT_W1TC_REG as *mut _, pins); }
}
```

where each bit in `pins` marks which bit will be set/cleared, as an example; calling `fast_pin_set(0b00000000000000000000000000010101)` will set the pins `[0, 2, 4]`.

knowing that, we can remove the branching & individual pin writes for the hot loop, like this:

```rust
let rgb = (r1 >> 5)
	| (g1 >> 2)
	| (b1 << 1)
	| (r2 << 15)
	| (g2 << 18)
	| (b2 << 21);
let not_rgb = !rgb & rgb_mask;
fast_pin_clear(not_rgb);
fast_pin_set(rgb & rgb_mask);
self.pins._clk.set_low();
self.pins._clk.set_high();
```
5bit = 25ms, 270% speedup

include clock in the blob set/clear:
```rust
let rgb = (r1 >> 5)
	| (g1 >> 2)
	| (b1 << 1)
	| (r2 << 15)
	| (g2 << 18)
	| (b2 << 21);
let not_rgb = !rgb & rgb_mask;
fast_pin_clear(not_rgb | (1 << clkpin));
fast_pin_set((rgb & rgb_mask) | (1 << clkpin));

```
5bit = 4.8ms (!!); 520% speedup. why does this change so much?

do the same to addr, 4.0ms
```rust
let addrdata: u32 = (i as u32) << 12;
let not_addrdata: u32 = !addrdata & addrmask;
fast_pin_clear(not_addrdata);
fast_pin_set(addrdata);
```
change data format to remove all bit shifting - mention pin reordering to match


116ms -> 4ms; 29x total speedup; fairer would be 67ms->4ms; 16x speedup

### Result

This is with 6 bit color depth, each frame takes 7.9ms to render

<video src="/videos/esp32-rust-projects/hub75-done-nyan.mp4" controls></video>

### Problems

I wanted a higher resolution for a project, so I bought some screens which use an extra address pin (`E`) and the ESP32 does not have any more contiguous pins.
This requires some shuffling of the address values (`(addr & 0b1111) | (addr & 0b10000) << n`) which slows down the frame to XXX ms.

On top of that, I chose a resolution of 128x64, 4 times as much as the numbers we were working with so far; on a 6-bit depth that'd be 32ms per frame which very visibly flickers.

Going to 5-bit depth halves the required time, to 16ms which is barely enough.

## "Hardware" implementation

something on the RP2040 PIO


---
title: Exploring HUB75
date: 2024-03-20
tags: rust, esp32, embedded, rp2040
slug: exploring-hub75
description: Driving a HUB75 display from ESP32 and RP2040
---


I bought some "HUB75" displays which are quite interesting because they do not self-refresh, instead you have to constantly drive each LED with the desired value, and as the LEDs are only "1-bit" (meaning that they can be on or off) you can't just set a specific color (eg: blue to 187).

However, these panels have a high refresh rate, so we can emulate color depth by quickly toggling the right LEDs on and off.


## Colors

What we consider normal colors are usually represented in 3 channels, R, G and B, each channel with an {^8-bit range|0-255}. The color white is represented as `#ffffff`, which is `255` (`0xff`) on all three channels.

<center>
	<img width="70%" src="/images/hub75/channels_exploded.svg"/>
</center>

In the same fashion that white can be split into three channels, we can split each channel into a bit plane; paraphrasing [Wikipedia](https://en.wikipedia.org/wiki/Bit_plane), a bit plane is a set of bits corresponding to a given bit position in each of the binary numbers representing the signal.

If we take the blue channel as an example (only 4 bits for easier representation)

<center>
	<img width="70%" src="/images/hub75/bitplane_exploded.svg"/>
</center>

Each bit-plane must be displayed for different lengths of time, otherwise the pattern `1100` and `0011` would be visible
as the same color.

To represent these bit-planes according to the color we'd expect, we can display each bit for twice as long as the previous
one and let our eyes do the "integration" of the image brightness.

In this case we'd be displaying the {^MSB|most significant bit} for 8 "periods", the next one for 4, then 2, then 1. 

Displaying brightness this way is called [binary coded modulation](http://www.batsocks.co.uk/readme/p_art_bcm.htm) or BCM.

Another example, representing a color with multiple channels as bitplanes over time:

<center>
	<img width="90%" src="/images/hub75/rgb_exploded.svg"/>
</center>

Here, this Magenta (`#d80073`) is only composed of the red and blue channels, so the green channel always stays off.

Taking the 4 most-significant-bits of each channel, we have `R = 0b1100 (0xd)` and `B = 0b0111 (0x7)`

## HUB75 protocol

The basic operation of the display:

- Select the current row with the pins A, B, C, D
- Place the corresponding bit for the R1, G1 and B1 channels on the input, then shift it into the display by bringing `CLK` up and down
- When the current row is complete, bring `LATCH` up and down

This lets you display an entire row of data. Repeat this with different values for A/B/C/D and you can shift in an entire bit plane.

In this case, we are shifting the 3 (R, G, B) bitplanes at once; on top of that, these displays usually populate two rows in parallel: [row index] and [row index + 16]; the second row is fed (R2, G2, B2).

## Math

For a given color depth D, we need to shift in 2<sup>D</sup> bitplanes, which are composed of R rows and C columns.

Taking my display as an example (64 columns, 32 rows) and a 4 bit depth image, we would need to clock in 2<sup>4</sup> * 64 * 32 = 32768 pixels

Going to 5 bit depth doubles the pixels per frame to 65536 and 6 bit to 131072.

## Software implementation

As the protocol does not rely on a fixed clock, we can shift data in as fast/slow as we want, which leaves a lot of room
to [bit-bang](https://en.wikipedia.org/wiki/Bit_banging) the protocol


We can manipulate each pin individually, as an example ([code](https://github.com/DavidVentura/hub75-esp/blob/1d14ca3713b7ee1625bf3dc9b1c6a54c50e3b75c/src/hub75.rs)):
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

Displaying a 5-bit image this way takes 116ms, which is very visibly flickering - each row is only being driven 1/16th of the total time, so each row is on for 7 ms, then off for 109ms.

Some simple optimizations:

* Increasing clock speed from 160MHz to 240MHz by setting `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y` results in a 77ms frame time
* Optimizing build by setting `lto = true` in `Cargo.toml` results in a 67ms frame time

### Batching writes

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

Knowing that, we can remove the branching & individual pin writes on the hot loop:

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
Now the time per frame is down to 25ms, which is a huge improvement, but still flickery.

We can also include clock in the batch set/clear, as this is executed 65k times per frame:
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

This brings the time down to 4.8ms (!!)

### Adjusting data format

While we no longer have any branches in the hot loop, we are still doing 6 bit shifts, which can be avoided.

Ideally, we could pre-format the data to not require any shifts, something like `pixels = XXRGB_RGB`, then write the lower 6 bits straight to the `W1T` register; however the ESP32 does not really expose 6 contiguous pins that can be written to.

The ESP32 does have multiple groups of 3 pins which only have 1 gap, and this can be useful, as we only need to shift out 6 bits of data per pixel.

The groups I picked for RGB1 and RGB2 are `[2, 4, 5]` and `[18, 19, 21]`.

By packing the pixel data as `pixel = R1__G1B1R2G2__B2`, the only computations needed in the inner loop are 2 shifts and 2 masks:

```rust
let rgb1 = *element as u32 & 0b1101_0000;
let rgb2 = *element as u32 & 0b0000_1011;
// The base of RGB1 is at pin 2
let pixdata: u32 = rgb1 >> 2;
// The base of RGB2 is at pin 18
let pixdata = pixdata | (rgb2 << 18) | (1 << clkpin);
```

This gives another 20% improvement, bringing the time per frame down to 3.95ms.

### Result

This is with 6 bit color depth, each frame takes 7.9ms to render

<video src="/videos/hub75/lowres.mp4" controls loop></video>

### Problems

I wanted a higher resolution for a project, 128x64, which 4 times as much as the numbers we were working with so far; on a 6-bit depth that means each frame takes 32ms to render, which very visibly flickers.

<video src="/videos/hub75/highres.mp4" controls loop></video>

Lowering the color depth to 5 bit halves the time per frame to 16ms which looks smooth if you are stationary, but if you move it definitely looks 'off'.


## "Hardware" implementation

I didn't want to figure out how to get the `I2S` peripheral on the ESP32 to work as I needed, I thought it'd be super frustrating, so instead I wrote a `PIO` program for the Raspberry Pi Pico.

To drive the screen in its most basic way, I used two state machines and fed them from the ARM core. I have some ideas on how to use 4 state machines and DMA to not use the ARM core at all, but this project's taken long enough already.

The first state machine drives the data & clock pins:

```asm
.wrap_target
    ; Auto-pull blocks & shifts 32 bits into OSR

    in osr, 8        [0] side 0 ; 8 lowest OSR bits into ISR (xxRGBRGB)
    out null, 8      [0] side 0 ; shift 8 zeroes into OSR
    mov pins, isr    [1] side 1 ; col 0 & clock posedge

    in osr, 8        [0] side 0 ;
    out null, 8      [0] side 0 ; shift 8 zeroes into OSR
    mov pins, isr    [1] side 1 ; col 1 & clock posedge

    in osr, 8        [0] side 0 ;
    out null, 8      [0] side 0 ; shift 8 zeroes into OSR
    mov pins, isr    [1] side 1 ; col 2 & clock posedge

    in osr, 8        [0] side 0 ;
    out null, 8      [0] side 0 ; shift 8 zeroes into OSR
    mov pins, isr    [1] side 1 ; col 3 & clock posedge

.wrap
```

The second state machine drives the 5 address pins, along with the `latch` and `OE` pins (copied from the example implementation):

```asm
.wrap_target
    ; Auto-pull blocks & shifts 32 bits into OSR

    out pins, 5 [2]    side 0b00 ; oe=1; latch=0
    out x, 27   [2]    side 0b11 ; oe=1; latch=1
pulse_loop:
    jmp x-- pulse_loop side 0b00 ; oe=0; latch=0
.wrap
```

The two state machines synchronize thanks to having auto-pull enabled, which will block reads from the `OSR` if there's no data.

With PIO, a 6-bit, 128x64 image can be rendered in 1.8ms, about 17x faster than the bit-banged ESP32 implementation.

This is also about the limit on the display anyway, as rising the clock on the PIO causes ghosting on the images.


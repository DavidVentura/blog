---
title: Exploring HUB75
date: 2024-03-15
tags: rust, esp32, embedded, rp2040
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

A bit plane of a digital discrete signal is a set of bits corresponding to a given bit position in each of the binary numbers representing the signal.
and if we take the same analogy, we can split a single _channel_ into different _bitplanes_ where a bitplane is 

<center>
	<img width="70%" src="/images/hub75/channel_exploded_bitplane.svg"/>
</center>

and making the bitplane relationship more explicit:

<center>
	<img width="70%" src="/images/hub75/bitplane_exploded.svg"/>
</center>

Each bit-plane must be displayed for different lengths of time, otherwise the pattern `1100` and `0011` would be visible
as the same pattern.

To represent these bit-planes according to the color we'd expect, we can display each bit for twice as long as the previous
one and let our eyes do the "integration" of the image brightness.

In this case we'd be displaying the {^MSB|most significant bit} for 8 "periods", the next one for 4, then 2, then 1. 

<center>
	<img width="70%" src="/images/hub75/bitplane_over_time.svg"/>
</center>

Displaying brightness this way is called [binary coded modulation](http://www.batsocks.co.uk/readme/p_art_bcm.htm) or BCM.

With all of these concepts in mind, we can display an image on the HUB75 displays.

### Protocol

The basic operation of the display:

- Select the current row index with the pins A, B, C, D
- Place the corresponding bit for the R1, G1 and B1 channels on the input, then shift it into the display by bringing `CLK` up and down.
- When you are done with the current row, bring `LATCH` up and down.

This lets you display an entire row of data. Repeat this with different values for A/B/C/D and you can shift in an entire bit plane.

In this case, we are shifting the 3 (R, G, B) bitplanes at once; on top of that, these displays usually populate two rows in parallel: [row index] and [row index + 16]; the second row is fed (R2, G2, B2).

### Math

For a given color depth D, we need to shift in 2<sup>D</sup> bitplanes, which constitute of R rows and C columns.

Taking my screen as an example (64 columns, 32 rows) and a 4 bit depth image, we would need to clock in 2<sup>4</sup> * 64 * 32 = 32768 pixels

Going to 5 bit depth doubles the pixels per frame to 65536 and 6 bit to 131072.

### Software implementation

As the protocol does not rely on a fixed clock, we can shift data in as fast/slow as we want, which leaves a lot of room
to [bit-bang](https://en.wikipedia.org/wiki/Bit_banging) the protocol

Naive with `set_high()`/`set_low()`
like 80ms

We can manipulate each pin individually
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
	if element.b1 > 0 {
		self.pins.b1().set_high()?;
	} else {
		self.pins.b1().set_low()?;
	}
```

what's the cost of all these individual writes to register + error unwrapping?
write to all data values (most ops by far) with `write_volatile` to the mmap address

idk 100x faster

change data format to remove all bit shifting - mention pin reordering to match
idk 2x faster

do the same for remaining oe/lat/addr
idk 2x faster

Outcome:
<video src="/videos/esp32-rust-projects/hub75-done-nyan.mp4" controls></video>

#### Problems
problems: no more pins for the nice new 64 pix tall screens

test: toggle `E` bit with software, impact?

### "Hardware" implementation

something on the RP2040 PIO


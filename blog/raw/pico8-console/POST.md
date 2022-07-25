---
title: Making a handheld Pico8 console, part 1
date: 2022-07-24
tags: rp2040, sdl, embedded
description: Building a RP2040 based Pico-8 handheld console
---

A while ago I found out about a "fantasy console" named Pico-8, which is a nifty little target for writing *constrained* games and thought
"how hard could it be to build a hardware version of this?" (that could run some unmodified games) which has sent me down quite a deep rabbit hole

The Pico-8 console has well defined (although mildly vague) specifications:

* 128x128, 16 color display
* 4 audio channels, 8 waveforms
* 6 button controller, per player
* Games are written in Lua (~5.2)
  * Up to 2Mb of Lua memory may be used
* Games are packaged as "Cartridges" which are specified as:
  * 32KB data
  * 128x128 pixel sprite sheet
  * 128x32 tile map
  * 64 sound patterns
  * 64 music patterns

My initial idea was to implement this on an RP2040 mostly so I could name it "Pico on Pico" (and because the toolchain is quite nice); this later proved pretty unworkable.


## Getting started

As a first step, I went through the [FAQ](https://www.lexaloffle.com/pico-8.php?page=faq) which shows an animated "hello world"; this is a perfect first program to write.

The demo source looks like this:

```lua
function _draw()
  cls()
  for i=1,11 do               -- for each letter
    for j=0,7 do              -- for each rainbow trail part
      t1 = t + i*4 - j*2      -- adjusted time
      y = 45-j + cos(t1/50)*5 -- vertical position
      pal(7, 14-j)            -- remap colour from white
      spr(16+i, 8+i*8, y)     -- draw letter sprite
    end
  end

  print("this is pico-8", 37, 70, 14)
  print("nice to meet you", 34, 80, 12)
  spr(1, 64-4, 90) -- draw heart sprite
  t += 1
end
```

and is supposed to render like this:

<center>
![](/images/pico8/hello_p8.gif)
</center>

There are some things of note in this example snippet:

* The function `_draw` is called automatically by the [game loop](https://pico-8.fandom.com/wiki/GameLoop)
* There are some engine-defined functions (the "console API"?): `pal`, `spr`, `print`, `cos`
* Non-standard Lua syntax: `t += 1`

## The basic engine

Pico-8 operations **mostly** either put sprites on screen or alter the [draw state](https://pico-8.fandom.com/wiki/DrawState) (which makes future operations behave differently).

My implementation at this stage was:

* Parse cartridge format (text-based)
* Implement `spr` (copy a sprite from the cartridge to framebuffer)
* Implement `cls` (blank the framebuffer)
* Implement `pal` (swaps indexes on palette, making future `spr` render with different colors)

And yes, this was missing `print`, but that'll come later

## Displaying something on screen

I knew from the beginning that doing embedded-only development was going to be too painful, so I should write the game "engine" in such a way that it could be (mostly) used on a desktop environment, with some kind of pluggable back-ends for embedded targets.

Started by following [Lazy Foo's tutorials](https://lazyfoo.net/tutorials/SDL/index.php) as SDL seemed like a reasonable level of complexity/abstraction for my skills (which, in this area, are zero).

After I managed to display something on my screen, I followed [this tutorial](https://lucasklassmann.com/blog/2019-02-02-how-to-embeddeding-lua-in-c/) on embedding Lua in C, which was surprisingly easy, although, obviously, Lua5.2 does not support the custom Pico-8 extensions to the syntax, so I altered the hello world for now.

## Running on hardware

With something basic that'd display on SDL, I wanted to define a reasonable abstraction for the different backends, I settled with this API

```c
bool init_video(); // false on failure to init
void video_close();
void gfx_flip();
void delay(uint16_t ms);
bool handle_input(); // true to quit
uint32_t now();
```

and started writing the implementation for the Pico. For display/video, I chose an ST7735-based display only based on the fact that it'd ship quickly and there seemed to be some drivers already implemented online.

I cloned the drivers, compiled the Pico port and got something on the display:

<center>
  <video controls>
    <source src="/videos/pico8/first_day_pico.mp4">
  </video>
</center>

which, while it made me _very_ happy, it had some pretty clear issues:

* It is _so slow_
* Colors are wrong (top-most "hello world" should be white)
* The curve (path? arc?) followed by the words is incorrect

## Improving the ST7735 driver

The driver I found online had a lot of features, drawing lines, shapes, words, colors, etc, but I needed none of that, all I needed was blitting entire framebuffers to screen.

When looking at the driver code, I saw that the `blit` operation was calling `set_pixel` in a loop, which is very slow, as it has to start an SPI transaction each time. I replaced this function with my own [send\_buffer](https://github.com/DavidVentura/PicoPico/blob/master/st7789.c#L16), which would just send the entire framebuffer in one go.

While I was poking in the driver, I also changed the expected color format from BGR to RGB, and this was the result:

<center>
  <video controls>
    <source src="/videos/pico8/pico-hello-world.mp4">
  </video>
</center>


## Improving the developer experience

The dev cycle up to this point was pretty atrocious, to get a build onto the RP2040 I had to:

 * Unplug the pico
 * Press bootsel while re-plugging the pico
 * Mount the pico
 * Drag & drop the new files

All of this.. to see my code crash slightly farther down the line.

So I added a "debug step" into the input polling function: a mechanism to reset into "Mass storage" mode when receiving "r" over usb-uart.. at least I could skip the "unplug, press, replug" part.

```c
    int c = getchar_timeout_us(0);
    switch (c) {
	case 'r':
	    reset_usb_boot(0, 0);
	    break;
    }
```

This snippet improved my dev life _dramatically_.

Afterwards I also added a udev script that automatically mounts & copies the latest build to the RP2040 when it is detected. This means that pressing "r" over UART will end up with a new build in the pico in ~8s.


## Supporting Lua language extensions

As Pico-8 uses a "custom" Lua, which has some language extensions but most importantly, it uses [fixed-point arithmetic](https://en.wikipedia.org/wiki/Fixed-point_arithmetic), I looked around a bit and luckily found [z8lua](https://github.com/samhocevar/z8lua): A Lua fork for the Pico-8 syntax

Integrating z8lua into the build was trivial at first. It built and ran just fine on the SDL port, but when I tried to run it on the RP2040 I got tons of type-casting errors, as the RP2040 is a 32 bit architecture.

After hours of manually casting to proper type widths (fork [here](https://github.com/DavidVentura/z8lua)), it finally compiled, but it would crash immediately on the Pico. Took me a while to figure out that `luaL_checkversion` can return errors, and the error it returned was perfectly clear:

> bad conversion number-\>int; must recompile Lua with proper settings

I then changed `LUA_INT32` and `LUA_UNSIGNED`, fixed more type casts and managed to run `z8lua` on the Pico. Now it has support for the `+=` operator, yay!

## Source

You can find the repo with the sources + schematic [here](https://github.com/DavidVentura/PicoPico).

## References

- [Pico-8 Wiki](https://pico-8.fandom.com/wiki/Pico-8_Wikia)
- [Getting started with RP2040](https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf)
- [RP2040 C SDK](https://datasheets.raspberrypi.com/pico/raspberry-pi-pico-c-sdk.pdf)

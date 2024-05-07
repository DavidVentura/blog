---
title: Pico8 console, part 2: performance
date: 2022-07-25
tags: rp2040, sdl, embedded, pico8, picopico, lua
description: Improving the performance of my RP2040 based Pico-8 handheld console
---

In [part 1](https://blog.davidv.dev/making-a-handheld-pico8-console-part-1.html) I got to a point where I had:

* Basic engine running in SDL / RP2040
* Reasonable development workflow
* A terribly slow hello world

In this post I'll dive into the rabbit-hole I found myself in when looking to improve performance

## Basic tests

The "hello world" demo currently takes 21ms to render a **single frame**, putting a hard limit of ~45fps on it.  This is quite terrible, as more complex games would take longer to render and be limited even further.

At this level of granularity, a simple time delta between each draw call is enough to determine that

* The Lua `_draw` function takes ~9ms to complete
* Copying the buffer over SPI to the display takes ~12ms

The first step I took was to change the default SPI clock rate from ~30MHz to 62.5MHz (based on [GameTiger's repo](https://github.com/codetiger/GameTiger-Console)), making the framebuffer copy take ~5ms. **Time per frame: ~21ms &rarr; ~17ms**

Afterwards, I moved the framebuffer copy step to the second core, which, while it took the same amount of time, it no longer blocked the render cycle. **Time per frame: ~17ms &rarr; ~12ms**. This was **so easy**:

* call `multicore_launch_core1(put_buffer)` on engine init
* have `put_buffer` block on a queue (`multicore_fifo_pop_blocking()`)
* have the `gfx_flip` platform-specific engine function push into this queue `multicore_fifo_push_blocking`

Overclocked the RP2040 to 260MHz,.  **Time per frame: ~12ms &rarr; ~5ms**

Inlined `put_pixel` (internal function for sprite rendering),  **Time per frame: ~5ms &rarr; ~4.5ms**

Now this puts a hard limit for "hello world" of ~200FPS which, while still slow, is not unreasonable.

## Other improvements

Pico-8 defines a basic color palette with 16 colors, and I'd naively declared a struct with the values as they were:

```c
static const color_t original_palette[] = {
    {0,    0,  0},     // black
    {29,  43, 83},     // dark-blue
    {126, 37, 83},     // dark-purple
    // ...
```
which would be _fine_ if I could use those values as they are. However, the display I'm using expects RGB565 values, and I was performing the transformation on 
every pixel copy (sprites, background, plain pixel), so I thought, what if I frontload that work?

```c
#define to_rgb565(r, g, b) (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
static const color_t original_palette[] = {
    to_rgb565(0,   0,  0),      // black
    to_rgb565(29, 43, 83),      // dark-blue
    ...
```
this brought the average ms/frame on [Celeste](https://www.lexaloffle.com/bbs/?tid=2145) from 16.21ms to 13.94ms (averaged over 100 frames), a nice 16% speedup.

## The nightmares begin: Rockets!

[Rockets!](https://www.lexaloffle.com/bbs/?tid=47633) is a very basic, yet entertaining game where you play as a small plane that has to dodge rockets. Here's a short video:

<center>
  <video controls=true>
    <source src="/videos/pico8/rockets.webm">
  </video>
</center>

The problem? the Lua logic to draw each frame takes **71ms** while the budget is 16ms (including SFX, input, buffer copies, etc)

Looking at the source code, it is pretty clear that the `spr_r` function is taking ~95% of the time. This function takes sprites and performs 
a rotation on them, by reading each pixel from the sprite buffer and painting each (transformed/rotated) pixel to the screen.

Given the sprites are 8px by 8px, the inner loop of this function executes 400 times, per frame, per sprite.

```lua
function spr_r(s,x,y,a,w,h)
    sw=(w or 1)*8
    sh=(h or 1)*8
    sx=(s%8)*8
    sy=flr(s/8)*8
    x0=flr(0.5*sw)
    y0=flr(0.5*sh)
    a=a/360
    sa=sin(a)
    ca=cos(a)
    for ix=sw*-1,sw+4 do
        for iy=sh*-1,sh+4 do
            dx=ix-x0
            dy=iy-y0
            xx=flr(dx*ca-dy*sa+x0)
            yy=flr(dx*sa+dy*ca+y0)
            if (xx>=0 and xx<sw and yy>=0 and yy<=sh-1) then
                pset(x+ix,y+iy,sget(sx+xx,sy+yy))
            end
        end
    end
end
```

There are some issues here, the biggest is architectural: there are only 2 sprites and a fixed amount of possible rotations, the values 
should be pre-computed and cached / stored in the sprite map, instead of being calculated on every frame, for every live object. I will _not_ address this as part of 
the goal for the console was to play games unmodified[^1].

The second issue is the fact that these variables are not declared as `local`s; in Lua, all variables default to being globals unless they are prefixed with the 
`local` keyword.

The third issue is the fact that these are performing a significant amount of floating-point work on a tight loop, and these operations are extremely slow.

### Lua and local/global variables

A two minute introduction into Lua would be:

Lua parses input code into bytecode, which then executes in a register-based virtual machine. This virtual machine has a lot of operations[^2], most of which directly operate on registers.

There are two scopes for variables: `local` and `global`. The difference being that Lua splits scopes into `chunks`, and variables of type `local` only live within a particular chunk. `global` variables exist globally, in an interpreter-defined table named `_g`.

The performance problem with the code above is that accessing global variables is significantly slower, the bytecode[^3] looks something like this:

```lua
b = 1
```

```
1	SETTABUP	0 -1 -2	; _ENV "b" 1
```

Lua's instructions are quite dense, this would translate to:

1. Fetch the constant at index -1 ("b")
2. Index the UpValue table (hashmap, defined outside this `chunk`, global) with the constant found (`b`)
3. Store the value from constant (indicated by the negative index) 2 in table entry

This (or very similar) happens every time you _read or write_ to a global variable.

In contrast, when using local variables

```lua
local b = 1
```

```
1	LOADK	0 -1	; 1
```

1. Place the constant (indicated by the negative index) found at index 1 in register 0

The time taken on these two cases is significantly different - the global access requires many more memory lookups and a hash calculation

If I manually convert the first lines of the codeblock to use local variables (literally prepending `local` to the first few lines of the block), the time 
per frame goes from **71ms/frame &rarr; 29ms/frame** (budget is <16ms/frame). However, as I said before, manual code changes to games is a no-go for this project.

### Floating point on embedded

The game loop calculates rotation using `sin`, `cos` and `flr`, which are currently just calling the C math functions that operate on floats.

A quick microbenchmark to measure the lower bound

```c
#pragma GCC push_options
#pragma GCC optimize ("O0")
int _noop(int arg) {
    return arg;
}
void bench_me() {
    uint32_t bstart = now();
    int res = 0;
    z8::fix32 n = 5;
    for (uint16_t i=0; i<32000; i++) {
        res = sin(i); // <- this `sin` call is the target of the optimization
    }
    printf("sin bench took %d; result is %d\n", now()-bstart, res);
}
#pragma GCC pop_options
```

shows that 32k calls (in C, with -O0) take ~550ms. The same thing in Lua takes ~735ms.

By adapting [this](https://www.nullhardware.com/blog/fixed-point-sine-and-cosine-for-embedded-systems/) implementation of fixed-point sin calculation, the execution time dropped to:

* C, -O0, 32k calls, 50ms
* Lua, 32k calls, 135ms

The overhead of Lua function calls starts to show.

After changing the implementation to call the fixed-point `sin` implementation, the time per frame barely changed. There's only one sin/cos call per object, and ~400 iterations of the inner loop. 

## Bytecode optimization

There are two clear things that can be optimized in the generated bytecode:

1. Optimized byte code for calls (to avoid looking up the functions)
2. Variable localization

On fastcalls, I [gave it a shot](https://github.com/DavidVentura/z8lua/commit/201aa808ca1e0b0529a6d9af0c80307fec263d92) but while this bytecode removes the need for looking up the function to call and placing the result in the stack, I did not manage to remove the lookups from the bytecode.

The code path here is measurably faster than the regular `call` path; **frame time 71ms &rarr; 65ms** (~9%)

For "localizing" variables, it is doable, but hard, it implies:

1. Identify which variables are not used (by name) in other chunks
1. Create space for "local variables" in the chunk stack
1. Remove unnecessary constants from the chunk constants
1. Replace `GETTABUP`s (load from UpVal table) with `LOADK` (load from register)

This [mostly worked](https://github.com/DavidVentura/lua-bytecode-optimizer); although ended up with spurious `LOADK` into `MOVE` and `MOVE` (stack variables) into registers, all of which could be optimized away.

The code I wrote was not sound, and because the amount of instructions had to change, I had to adjust a lot of relative jumps, etc. It was harder than expected and I couldn't really get it working. Maybe I should revisit it and add NOPs instead.

## Next steps

Currently, I've given up on the bytecode-optimizer and am instead looking at ahead-of-time (AOT) compilation: generating C++ code from the Lua input. It is promising, but buggy.

## Source

You can find the repo with the sources + schematic [here](https://github.com/DavidVentura/PicoPico).



[^1]: At least, without any manual modifications
[^2]: Greatly documented [here](https://the-ravi-programming-language.readthedocs.io/en/latest/lua_bytecode_reference.html)
[^3]: [This decompiler](https://www.luac.nl/) is very useful

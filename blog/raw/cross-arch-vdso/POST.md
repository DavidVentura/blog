---
title: Investigating crashes on self-modifying code
date: 2024-03-28
tags: riscv, aarch64
slug: self-modifying-code-crashes
description: Replacing vDSO entries on more architectures with a bang
---

I wanted to run some [self-modifying code](/cursing-a-process-vdso-for-time-hacking.html) on my "[cluster](/cross-arch-nomad.html)", which includes RISC-V and AArch64 {^SBCs|single board computers}, but as soon as I ran the project on these boards, I noticed that it would _sometimes_ crash with `SIGBUS` or `SIGSEGV`.

The execution flow of the program:

```c
function();
*function = new_code;

function();
*function = original_code;

function(); // sometimes crashes here
```

I dumped both the original function memory and the restored function memory area, they always were identical, so I was not restoring bad values onto the original addresses.

To make things weirder:

* The crash is less likely (but still happening) if there's a `sleep(..)` after restoring the original code.
* The crash 100% goes away if there's a breakpoint after restoring the original code.


Analyzing the crash, the test application logs:
```
writing 0x2a0 bytes to 0xfffff7ffc2c0
```

and proceeds to crash:
```
Program received signal SIGSEGV, Segmentation fault.
0x52800022540005e8 in ?? ()
```

The code on the function segment looks right
```
(gdb) x/5i 0xfffff7ffc2c0
   0xfffff7ffc2c0 <__kernel_clock_gettime>:     paciasp
   0xfffff7ffc2c4 <__kernel_clock_gettime+4>:   cmp     w0, #0xf
   0xfffff7ffc2c8 <__kernel_clock_gettime+8>:   b.hi    0xfffff7ffc384 <__kernel_clock_gettime+196>  // b.pmore
   0xfffff7ffc2cc <__kernel_clock_gettime+12>:  mov     w2, #0x1                        // #1
   0xfffff7ffc2d0 <__kernel_clock_gettime+16>:  mov     w3, #0x883                      // #2179
```

But when looking at the same code as hex values:
```
(gdb) x/10x 0xfffff7ffc2c0
0xfffff7ffc2c0 <__kernel_clock_gettime>:        0xd503233f      0x71003c1f      0x540005e8      0x52800022
0xfffff7ffc2d0 <__kernel_clock_gettime+16>:     0x52811063      0x1ac02042      0x10fee944      0x6a030043
0xfffff7ffc2e0 <__kernel_clock_gettime+32>:     0x54000640      0x8b20d089
```

I noticed that the program counter is set to the data at `__kernel_clock_gettime+8` -- the program tried to jump there, but there's no `br` instruction in this code!

The trampoline code _does_ call `br` on `PC+8`:

```asm
ldr x0, 8 			; load to x0 the value at PC+8
br x0 				; jmp
.dword 0xffffffffff ; 8 bytes of data
```
but that's not the code we are currently executing!

To validate this hypothesis, I updated the trampoline code with some padding:

```asm
ldr x0, 16 			; load to x0 the value at PC+16
br x0 				; jmp
nop 				; padding
nop 				; padding
.dword 0xffffffffff ; 8 bytes of data
```

The program still crashed
```
Program received signal SIGBUS, Bus error.
0x1ac0204252811063 in ?? ()

(gdb) x/5i 0xfffff7ffc2c0
   0xfffff7ffc2c0 <__kernel_clock_gettime>:     paciasp
   0xfffff7ffc2c4 <__kernel_clock_gettime+4>:   cmp     w0, #0xf
   0xfffff7ffc2c8 <__kernel_clock_gettime+8>:   b.hi    0xfffff7ffc384 <__kernel_clock_gettime+196>  // b.pmore
   0xfffff7ffc2cc <__kernel_clock_gettime+12>:  mov     w2, #0x1                        // #1
   0xfffff7ffc2d0 <__kernel_clock_gettime+16>:  mov     w3, #0x883                      // #2179

(gdb) x/10x 0xfffff7ffc2c0
0xfffff7ffc2c0 <__kernel_clock_gettime>:        0xd503233f      0x71003c1f      0x540005e8      0x52800022
0xfffff7ffc2d0 <__kernel_clock_gettime+16>:     0x52811063      0x1ac02042      0x10fee944      0x6a030043
0xfffff7ffc2e0 <__kernel_clock_gettime+32>:     0x54000640      0x8b20d089
```

But now the value in PC is `__kernel_clock_gettime+16`!

This implies that we are executing the old instructions (trampoline) _with the updated data!_.

## Cache coherency
At this point I thought that it's likely that the D-cache and I-cache are not coherent - I'd expect both to read from the old or new data in memory, but that's not what's happening.

My expectation was that this would be done automatically by the kernel every time `mprotect` is called on a given memory region, but researching a bit I found [this discussion](https://patchwork.kernel.org/project/linux-arm-kernel/patch/1464088597-8820-1-git-send-email-thunder.leizhen@huawei.com/) which contains this relevant snippet:

> Subsequent changes to this mapping or writes to it are entirely the responsibility of the user.
> So if the user plans to execute instructions, it better explicitly flush the caches

When looking on how to flush these caches, I found an [ARM blog post](https://community.arm.com/arm-community-blogs/b/architectures-and-processors-blog/posts/caches-and-self-modifying-code), which mentions that GCC has a built-in ([`__clear_cache`](https://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html#index-_005f_005fbuiltin_005f_005f_005fclear_005fcache)) specifically designed to clear the D/I caches in a given range. 

## Solution

I needed to call a GCC/LLVM builtin, but `rustc` does not expose it. I could/should have yoinked the code from LLVM/GCC's implementation but instead I chose to rely on their implementation by creating a static, shared library ([cacheflush-sys](https://github.com/DavidVentura/cacheflush-sys)) which only exports the compiler built-in.

```c
volatile void clear_cache(void* start, void* end) {
    __builtin___clear_cache(start, end);
}
```
Having the ability to make the data/instruction caches coherent again, I [changed](https://github.com/DavidVentura/tpom/pull/4/files) the `overwrite` implementation to be basically:

```rust
mprotect(READ | WRITE | EXECUTE);
memcpy(__kernel_clock_gettime, ...);
mprotect(READ | EXECUTE);
cache_flush(__kernel_clock_gettime, trampoline_len);
```
with this change, the program stopped crashing on AArch64 and RISC-V


References:
* [Similar issue in dotnet](https://github.com/dotnet/runtime/issues/8825) 
* [`__clear_cache` reference](https://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html#index-_005f_005fbuiltin_005f_005f_005fclear_005fcache)
* [How does `__builtin___clear_cache` work?](https://stackoverflow.com/questions/35741814/how-does-builtin-clear-cache-work)

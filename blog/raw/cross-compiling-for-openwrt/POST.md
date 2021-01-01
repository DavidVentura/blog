I own a TP-Link X which is an [ath79](https://openwrt.org/docs/techref/targets/ath79) based wireless router, which runs OpenWrt.

I've been trying to get some specific software running on the router to do wifi-based presence detection to enable some automation, and I thought it'd be nice to get some experience doing this in rust.


# Compiling for the target

First, for the most basic case, I'd like to get the most minimal program possible running on the device itself - which has a MIPS processor. Let's try that.

```c
int main()
{
        return 42;
}
```

Having this minimal program we can install `gcc-9-mips-linux-gnu` and cross compile it:

```bash
$ mips-linux-gnu-gcc-9 ./a.c
```

after moving `a.out` to the router and moving it we can see it does not work:
```bash
root@OpenWrt:~# ./a.out
-ash: ./a.out: not found
root@OpenWrt:~# ldd a.out
        /lib/ld.so.1 (0x77eb0000)
        libc.so.6 => /lib/ld.so.1 (0x77eb0000)
```

Looking at the `lib` path we can indeed see we do not have `ld.so.1`.
The binary is trying to use the linker in this path because our cross-compiler doesn't know which dynamic linker to use in this platform - so it's using the same that we are using right now.

If we check the dynamic linker on the router itself and pass it to the compiler:

```bash
root@OpenWrt:~# ls /lib/ld*
/lib/ld-musl-mips-sf.so.1
```

We can now compile the binary and specify which linker to use, then run it remotely:

```bash
$ mips-linux-gnu-gcc-9 -Wl,--dynamic-linker=/lib/ld-musl-mips-sf.so.1 ./a.c
..
root@OpenWrt:~# ./a.out
root@OpenWrt:~# echo $?
42
```
It works!

## Using libraries

Let's try a slightly more complicated program:
```c
#include <stdio.h>
int main()
{
        printf("%d\n", 1234);
}
```

Running the new program shows some errors this time though
```bash
root@OpenWrt:~# ./a.out
Error relocating ./a.out: __printf_chk: symbol not found
root@OpenWrt:~# ldd a.out
        /lib/ld-musl-mips-sf.so.1 (0x77f36000)
        libc.so.6 => /lib/ld-musl-mips-sf.so.1 (0x77f36000)
Error relocating a.out: __printf_chk: symbol not found
```

This is because the `libc` I linked (glibc) is not compatible with the libc in the router (musl).

I could keep hacking at errors as they pop up, but I presume they will be plenty as the entire environment is different.
Usually for cases like this what you have to use is the same `toolchain` as the developers who built the distro (in this case, the OpenWrt devs)

I [got the sdk](https://downloads.openwrt.org/releases/19.07.5/targets/ath79/generic/openwrt-imagebuilder-19.07.5-ath79-generic.Linux-x86_64.tar.xz) and followed some of [these directions](https://openwrt.org/docs/guide-developer/crosscompile) -- specifically setting the `PATH` and `STAGING_DIR`.

```bash
$ mips-openwrt-linux-gcc b.c
..
root@OpenWrt:~# ./a.out
1234
```

Success!

Let's repeat the whole thing with our rust program now:


# Compiling rust code for the target

Luckily rust brings a lot of modern tooling to the table, including the ability to cross-compile quite easily by adding targets:

```bash
$ rustup target list | grep mips | grep musl
mips-unknown-linux-musl
$ rustup target add mips-unknown-linux-musl
```

We can create a trivial project and cross-compile it:
```bash
$ cargo new trivial-project
$ cd trivial-project; cargo build --target mips-unknown-linux-musl
..
root@OpenWrt:~# ./trivial-project
Hello, world!
root@OpenWrt:~# ldd trivial-project
        /lib/ld-musl-mips-sf.so.1 (0x77ee6000)
        libgcc_s.so.1 => /lib/libgcc_s.so.1 (0x77e5a000)
        libc.so => /lib/ld-musl-mips-sf.so.1 (0x77ee6000)
```

This works! and rust knows which dynamic linker to use directly.

## Getting side-tracked: binary size

There is one initial 'problem' with the binary size: it's 3.2MB and our entire rootfs is *10.9MB*.

A trivial change to cargo's build can help us quite a bit with this 
```ini
[profile.release]
opt-level = 'z' # opt for size
lto = true
panic = "abort"
```

This drops the binary size from 3.2MB to 1.3MB. That's substantial. If you are interested in reducing this further, there's a very handy guide [on github](https://github.com/johnthagen/min-sized-rust).

Stripping the binary after that (`mips-linux-gnu-strip binary`) drops it to a respectable 285KB.

# Compiling the application for the target

In my case, what I want to build uses the MQTT protocol, for which the crate I picked uses the `libmosquitto` C-bindings.

When trying to build, this points towards another problem:

```
$ cargo build --target mips-unknown-linux-musl
mips-openwrt-linux-musl/bin/ld: cannot find -lmosquitto
```

Our linker cannot find `libmosquitto` because it needs a shared library compiled for the target architecture. Before linking to it, I know we should target the same ABI as what will be installed in the device, so I checked what's available in the package manager

```bash
root@OpenWrt:~# opkg list | grep libmosq
libmosquitto-nossl - 1.6.12-1
```

Cool, we need to get and cross-compile<sup><a href='#1'>[1]</a></sup> libmosquitto version 1.6.12

```bash
$ git clone https://github.com/eclipse/mosquitto.git
$ git checkout 1.6.12
$ export CROSS_COMPILE=~/openwrt-toolchain/bin/mips-openwrt-linux-musl-
$ export CC=gcc
$ make WITH_SRV=no WITH_WEBSOCKETS=no WITH_TLS=no WITH_DOCS=no WITH_CJSON=no -j
$ file lib/libmosquitto.so.1
lib/libmosquitto.so.1: ELF 32-bit MSB shared object, MIPS, MIPS32 rel2 version 1 (SYSV), dynamically linked, with debug_info, not stripped
```

Excellent! We have a library! At this point I spent a long while trying to get `cargo` to tell the linker where to find this library and failed -- I am not sure how to do that, so I did the next best thing: I put the library in the cross-compiler's path:

```bash
$ cp lib/libmosquitto.so.1 ~/openwrt-toolchain/lib/libmosquitto.so
```

Let's give that a try..
```bash
$ cargo build --target mips-unknown-linux-musl
...
Finished dev [unoptimized + debuginfo] target(s) in 0.44s
```

Nice! Let's check what's in the binary
```bash
root@OpenWrt:~# ldd ./wifi-presence
        /lib/ld-musl-mips-sf.so.1 (0x77f22000)
        libmosquitto.so.1 => /usr/lib/libmosquitto.so.1 (0x77ea8000)
        libc.so => /lib/ld-musl-mips-sf.so.1 (0x77f22000)
        libgcc_s.so.1 => /lib/libgcc_s.so.1 (0x77e84000)
        libssl.so.1.1 => /usr/lib/libssl.so.1.1 (0x77e04000)
        libcrypto.so.1.1 => /usr/lib/libcrypto.so.1.1 (0x77c2a000)
```

And let's run it:

```bash
root@OpenWrt:~# ./wifi-presence
Hello, world!
thread 'main' panicked at 'Failed!: Error { text: "connect: Invalid function arguments provided.", errcode: 3, connect:
false }', src/main.rs:24:11
```

Ha! Turns out this crate is a bit broken. There's [an open PR](https://github.com/stevedonovan/mosquitto-client/pull/10) for this issue, but seems to be ignored.

I guess I'll take a look at other crates or see if I can build my own crate with the patch.

<span id='1'>[1] maybe I could've just scp'd it from the router?</span>

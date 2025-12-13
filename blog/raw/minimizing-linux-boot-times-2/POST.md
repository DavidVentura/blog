---
title: Even faster Linux boot times
date: 2025-10-31
tags: firecracker, linux, optimization
slug: faster-linux-boot-times
description: Getting Linux to boot in 3ms
# series: Boot time optimization
incomplete: true
---

I've recently discovered [TinyKVM](https://github.com/varnish/tinykvm) and saw that they are using KVM for isolation without a kernel, where all syscalls are cheaply emulated, and it's amazing.

While beating something that _doesn't boot a kernel_ will be hard, I still want to see how close we could get by booting a real, functional, Linux kernel.

Functional only means: 64 bit kernel, VirtIO devices (including networking), non-emulated syscalls.

It doesn't mean silly things like "dynamic loaders", "persistent storage" or "multiple CPUs".


In the previous post in this series, I got a kernel to boot in 6.0ms+2.9ms of Firecracker overhead.

My setup changed in the meantime, so I need to re-run that experiment

The **new** testing environment consists of:
- My laptop (Ryzen 7 7840U, no tuning, kernel 6.8)
- A "default-sized" VM: 1 vCPU and 128MB RAM 
- A target kernel version 6.17.5
- Runtimes are measured by running every configuration 30 times and picking the lowest value[^cherrypick]

[^cherrypick]: Is it really a benchmark if you don't cherry pick the numbers?

## Setting up the environment

We need some stuff before we can even start testing.

On the host, we need a [tap interface](https://docs.kernel.org/networking/tuntap.html) for the VMs to use as their network device.

```text
sudo ip tuntap add dev tap0 mode tap
sudo ip addr add 10.0.0.0/24 dev tap0
sudo ip link set dev tap0 up
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward
```

Then, we are going to need a kernel image (`vmlinux`), I set mine up by disabling everything, then enabling:

- 64 bit support
- Virtio network
- /dev/mem support
- TTY
- Serial 8250
- Console on serial
- HID

and running `make -j16 vmlinux && strip vmlinux`

We are also going to need some kind of init program to send the 'boot complete' signal back to Firecracker

```c
int main () {
   dev_t devnum = makedev(1, 1);
   int fd = open("/mem", (O_RDWR | O_SYNC | O_CLOEXEC));
   int mapped_size = getpagesize();

   char *map_base = mmap(NULL,
        mapped_size,
        PROT_WRITE,
        MAP_SHARED,
        fd,
        0xd0000000);

   *map_base = 123; // writing 123 to `0xd0000000` is the boot-complete signal
   msync(map_base, mapped_size, MS_ASYNC);
   return 0;
}
```

then we need to build this program and pack it up in a [cpio archive](https://en.wikipedia.org/wiki/Cpio):

```bash
$ gcc -s -O2 -static init.c -o initramfs/a.out
$ (cd initramfs && find . | cpio -o -H newc > ../initramfs.cpio)
1445 blocks
```

<div class="aside">

The normal static binary is <b>huge</b>, the regular version clocks in at 702KiB for what is just a handful of syscalls.

There's the option of using <a href="https://lwn.net/Articles/920158/">nolibc</a> for simple programs, which provides very thin wrappers around syscalls:

```bash
$ gcc -fno-asynchronous-unwind-tables -s -Os -nostdlib -static -include nolibc.h -o initramfs/a.out init.c
```

The binary is now 8KiB (mostly padding), rejoyce!
</div>


### Measurements setup

I applied a [tiny patch](assets/timing.patch) on Firecracker to print timing information, which shows this:

```text
VM Request 1762097792.007193031
VM load_kernel+load_initrd 0.003697686
VM Created 1762097792.013032016
VM Booted  1762097792.019476580
```

With a little python script, I ran the VM creation 30 times and picked the fastest-booting one, which gave me 8.5ms as a starting point.

We can get a basic idea of what is taking time with [cargo-flamegraph](https://github.com/flamegraph-rs/flamegraph)

```text
cargo flamegraph -F 9997 --palette rust --min-width=5 --bin firecracker -- --no-api --config-file config.json --no-seccomp --boot-timer 
```

## Measuring

If we take the firecracker from the previous post, which included the hugepages patch, we can get a rough idea of where time is spent

![](assets/first_boot.svg)

A few things are immediately interesting:

- `drop_in_place` (second leftmost column) shows about 8% of the time is spent just _dropping_ the VM object
- `build_microvm_from_json` (large, middle column) takes about 65% of the total time

If we focus on the VM creation part:
![](assets/focus_json.svg)

We can see that the setup time is split between two main workloads:

- `load_kernel`, which takes about **80%**
- `create_vmm_and_vcpus` which takes about **15%**

In absolute terms, this is 42% and 8%.


This graph does NOT show the time spent executing the VM.

These flamegraphs were running a single VM, which is noisy and fixed startup costs show up as a large percentage of the
total. In _my_ real use case, a single process will spawn many VMs, so here's a flamegraph of a single firecracker
process spawning 10 VMs:

![](assets/10vms.svg)

## Optimizing VM setup

`load_kernel` seems to take ~3.3ms, and it is 
- parsing the elf
- 'volatile' reading the file

can we make it faster? surely yes

if we pre-read the kernel ONCE into a buffer, then copy the buffer over the VMs memory directly, it takes ~1.5ms, which
is about 45% of the original time.

FIXME timing -- 800µs in firecracker-new, even with same kernel, but HUGE variance

```
initrd addr = 134205440 size = 9728
loader offset 16777216, size 6641644
loader offset 25165824, size 913408
```

TODO can skip 2MB of the 6.6MB in the kernel => 30% faster?


```bash
perf record --call-graph dwarf -F max -g -- ./build/cargo_target/release/firecracker --no-api --config-file config.json --no-seccomp --boot-timer
perf script > out.perf
```

MAYBE note on mangling this a bit to make it more clear

pie chart, and mention that it's OVERHEAD ONLY -- the actual vCPU run happens in another thread -- or find how to measure?

--> vcpu_run is only scheduler/flush.. it's more time if i add sleep(1) inside, but not nearly enough. better to measure separately 

-> piechart of {memory setup, vm setup, boot time}

note that memory is always necessary, modify load_kernel to be memcpy -> make a trimmed flamegraph or a note

struggle with MMAP (private) to avoid copies on top of memfd/hugepages

find out if we need to copy the _entire_ kernel image or just a part? dump before and after, then compare?


maybe also, make a kernel that only halts (what do i need?) to measure pure overhead

```asm
BITS 64
global _start

_start:
    cli
    
    ; Page table setup omitted
    
    ; Write magic value to MMIO address
    mov rbx, 0xd0000000
    mov byte [rbx], 123
    
    ; clear interrupt table & force triple-fault reboot
    xor rax, rax
    lidt [rax]
    int 3
```

```ld
ENTRY(_start)

SECTIONS {
    . = 0x100000;  /* Virtual = Physical at 1MB */
    
    .text : {
        *(.text)
    }
    
    .bss : {
        *(.bss)
    }
}
```

```bash
nasm -f elf64 flat.S -o flat.o
ld -n -o flat.elf -T flat.ld flat.o
```

seems to be 50&ndash;75µs ??


---

then focus on kernel

LTO
host arch optimization

add the BOOT_TRACE macro -- note that it'll be cycles not µs and that measuring and printing skews real time, but relation between parts is fine.
- show that /dev/console takes a while, remove
- freeing kmem takes a while? remove
- measure hack disabling sleep()
- measure of input device i8042 was taking a long time
- measure serial probe + kvm exit -> comment out


finally, disable tty/serial, note that there's no output, so measuring now is quite hard, but it's good for the 'absolute' final number




love a good detour, add  linker script (ld) syntax support

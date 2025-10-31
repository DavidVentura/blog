---
title: Even faster Linux boot times
date: 2025-10-31
tags: firecracker, linux, optimization
slug: faster-linux-boot-times
description: Getting Linux to boot in 3ms
series: Boot time optimization
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

```bash
sudo ip tuntap add dev tap0 mode tap
sudo ip addr add 10.0.0.0/24 dev tap0
sudo ip link set dev tap0 up
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward
```


```bash
$ gcc -s -O2 -static init.c -o initramfs/a.out
$ (cd initramfs && find . | cpio -o -H newc > ../initramfs.cpio)
1445 blocks
```


TODO:

- re-run without patches
- show flamegraph+command

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

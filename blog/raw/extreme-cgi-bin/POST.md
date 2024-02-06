---
title: Extreme CGI bin
date: 2024-02-05
tags: firecracker, linux, optimization
description: "cgi-bin: the apotheosis of web development"
incomplete: yes
---

Once upon a time, we had [CGI-Bin](https://en.wikipedia.org/wiki/Common_Gateway_Interface) as means of interacting with incoming requests: when a request came in, the HTTP server started a new process to deal with it.

Each process only lived as long as the request, which meant no persistent state, and
no bugs from stale resources, or memory leaks.

In this regard computers _suck_ -- they live longer than the requests and have persistent state!


What if we could change that?

Introducing *Extreme CGI Bin*: Say goodbye to the tyranny of persistent state!

```
00.000000 Linux version 6.7.3 (david@dev) (gcc (Debian 12.2.0-14) 12.2.0, GNU ld (GNU Binutils for Debian) 2.40) #138 Tue Feb  6 16:15:23 UTC 2024
00.000970 Command line: earlyprintk=serial,ttyS0 console=ttyS0,115200 panic=-1 reboot=t no_timer_check printk.time=1  cryptomgr.notests tsc=reliable 8250.nr_uarts=1 iommu=off pci=off ip.dev_wait_ms=0 mitigations=off root=/dev/vda  ip=172.16.0.2::172.16.0.1:255.255.255.0:hostname:eth0:off quiet init=/initc root=/dev/vda ro virtio_mmio.device=4K@0xd0000000:5 virtio_mmio.device=4K@0xd0001000:6
00.001100 [Firmware Bug]: TSC doesn't count with P0 frequency!
00.001183 BIOS-provided physical RAM map:
00.001340 BIOS-e820: [mem 0x0000000000000000-0x000000000009fbff] usable
00.001501 BIOS-e820: [mem 0x000000000009fc00-0x000000000009ffff] reserved
00.001662 BIOS-e820: [mem 0x0000000000100000-0x0000000007ffffff] usable
00.001784 printk: legacy bootconsole [earlyser0] enabled
00.006415 [    0.004406] EXT4-fs (vda): write access unavailable, skipping orphan cleanup
00.008020 Hello!
00.008156 [    0.005152] Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000400
```
With *Extreme CGI Bin* you can boot into your application _with a network stack_ in 8 milliseconds[^1] or your money back!

---

Getting here took me a few days

As a baseline, using the same VMM (Firecracker) with their provided [example 5.10 kernel](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#running-firecracker) takes 1.037s to boot.

I thought that slowly analyzing every single active kernel feature for its impact on boot time was going to take too long if I was starting from a fully featured kernel.

Instead, I opted to start from the most minimal possible state, by compiling my own kernel with `make tinylinux`[^2] and working up to a kernel that would boot.

The first thing I knew is that I only needed:
- Virtio Storage
- Virtio Network 
- EXT4 filesystem
- IP stack

And things I wanted:
- 64 bit kernel
- TTY/Serial to see output
- Cgroups

With these options, I got a 1.6MB `bzImage` and a 13MB `vmlinux`.

I will conduct these tests in the "standard firecracker configuration" which is: 1 vCPU and 128MB RAM.

I built the most minimal C program which could show some signs of life

```c
#include <stdio.h>
int main() {
	printf("Hello!\n");
	return 4;
}
```

After running this as init, I did get the exit code[^3] on the panic logs:
```
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000400
```

but my `Hello!` message was nowhere to be found.

Reading the [firecracker docs](https://github.com/firecracker-microvm/firecracker/blob/main/docs/kernel-policy.md) I noticed that I also needed to enable `CONFIG_SERIAL_8250_CONSOLE`, and

```
[    0.004458] EXT4-fs (vda): write access unavailable, skipping orphan cleanup
Hello!
[    0.005957] Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000400
```

Success!

**Boot time: 11.1ms**.

### Trouble in paradise


When trying to run an equivalent golang program:

```go
package main

import (
	"fmt"
	"os"
)

func main() {
	fmt.Println("Hello Go!")
	os.Exit(5)
}
```

I would just get 
```
Kernel panic - not syncing: Requested init /goinit failed (error -8).
```

After enabling `CONFIG_IA32_EMULATION` I got a "way better" result:

```
futexwakeup addr=0x815ba50 returned -38
SIGSEGV: segmentation violation
PC=0x8077e12 m=2 sigcode=1

goroutine 0 [idle]:
runtime.futexwakeup(0x815ba50, 0x1)
    /home/david/.bin/go/src/runtime/os_linux.go:94 +0x82 fp=0x9437f7c sp=0x9437f50 pc=0x8077e12
runtime.notewakeup(0x815ba50)
    /home/david/.bin/go/src/runtime/lock_futex.go:145 +0x4b fp=0x9437f90 sp=0x9437f7c pc=0x80515bb
runtime.startlockedm(0x9406100)
    /home/david/.bin/go/src/runtime/proc.go:2807 +0x6a fp=0x9437fa0 sp=0x9437f90 pc=0x8082b7a
runtime.schedule()
    /home/david/.bin/go/src/runtime/proc.go:3628 +0x7d fp=0x9437fbc sp=0x9437fa0 pc=0x8084aed
runtime.park_m(0x9406600)
    /home/david/.bin/go/src/runtime/proc.go:3745 +0x167 fp=0x9437fd8 sp=0x9437fbc pc=0x8085237
runtime.mcall()
    /home/david/.bin/go/src/runtime/asm_386.s:329 +0x44 fp=0x9437fe0 sp=0x9437fd8 pc=0x80a5ed4
```

At least the runtime starts, though clearly it's missing something.

After trying a bunch of random things marked COMPAT I re-enabled `CONFIG_COMPAT_32BIT_TIME`, which worked!

```
[    0.004453] EXT4-fs (vda): write access unavailable, skipping orphan cleanup
Hello Go!
[    0.005732] Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000500
```

but this (`IA32_EMULATION` + `CONFIG_COMPAT_32BIT_TIME`) brought the boot time up by ~500µs (((.

**Boot time: 11.6ms**.

### Talking to the world
With a working kernel it's time to make this talk to the outside world!

We can set a [static IP configuration](https://docs.kernel.org/admin-guide/nfs/nfsroot.html) in the kernel command line by passing
```
ip=172.16.0.2::172.16.0.1:255.255.255.0:hostname:eth0:off
``` 

It's alive!
```
$ bash start-vm.sh 
$ ping 172.16.0.2
PING 172.16.0.2 (172.16.0.2) 56(84) bytes of data.
64 bytes from 172.16.0.2: icmp_seq=1 ttl=64 time=0.508 ms
64 bytes from 172.16.0.2: icmp_seq=2 ttl=64 time=0.364 ms
64 bytes from 172.16.0.2: icmp_seq=3 ttl=64 time=0.299 ms
64 bytes from 172.16.0.2: icmp_seq=4 ttl=64 time=0.273 ms
```

but.. now the boot time is at 31.7ms?? How could configuring a static IP take 20ms??

Looking at [kernel sources](https://github.com/torvalds/linux/blob/v6.7/net/ipv4/ipconfig.c#L1519) I found

```c
#define CONF_POST_OPEN 10
// ...
msleep(CONF_POST_OPEN);
```

right before the IP configuration started. I [made a patch](https://github.com/DavidVentura/fast-kernel-boot/blob/master/linux_sleep.patch)[^4] to disable this, and the regression went away.


**Boot time: 11.7ms**

### On memory sizing

I noticed that the boot time went up significantly when assigning larger memory sizes to the VM: 
<center>
![](/images/extreme-cgi-bin/boot_time_vs_memory_size_4k.svg)
</center>

All of this delta was spent setting up the kernel's page structures, which didn't make any sense to me.

I started commenting out chunks of the page table setup, but as long as _anything_ was done to the struct, the entirety of the time came back.
So this was not processing, but triggered by merely accessing the memory.

I'd remembered reading about a [similar project](https://www.usenix.org/publications/loginonline/freebsd-firecracker) which mentioned the constant page faulting and their attempt to solve it via the `MAP_POPULATE` flag.

I applied patch to firecracker, unconditionally passing `MAP_POPULATE` when creating the backing memory for the VM, and the boot time went down to 7.6ms!

This is 4ms that we were spending effectively page-faulting

However.. the time to create a VM went up:

* Pre-patch, all sizes: 77ms
* After-patch:
    * 128M: 119ms
    * 1024M: 340ms
    * 4096M: 920ms

This doesn't really help - as the kernel time goes down, but the wall time to launch the VM goes **up**.

Instead of doing this, I opted for a simpler way of reducing page faults: using hugepages.

I made a [simple patch](https://github.com/DavidVentura/firecracker/commit/6f14487e4642fc7a369016edcea9935d6e547677) for firecracker to allow specifying whether the VM's memory should be backed
by huge pages or not

<center>
![](/images/extreme-cgi-bin/boot_time_vs_memory_size.svg)
</center>

For a simple hello-world program, only 11 hugepages were touched:

```bash
$ cat /sys/kernel/mm/hugepages/hugepages-2048kB/free_hugepages 
1024
$ bash start-vm.sh 
$ cat /sys/kernel/mm/hugepages/hugepages-2048kB/free_hugepages 
1013
```

**Boot time: 8.06ms**

<!--
BOTH:
128: 90ms
1024M: 150ms
4096M:  420ms
-->

## Adding SMP?

If we want to support multi-core machines, then we need to enable SMP. Enabling SMP `CONFIG_SMP=y` instantly shoots up to 33ms, even with 1 vCPU!

I've not really dug into what's taking so long


[^1]: on my laptop, with a Ryzen 5 7640U, no tuning
[^2]: Thanks to the [kernel minification project](https://tiny.wiki.kernel.org/) 
[^3]: Why is the exit code shifted left 1 byte?
[^4]: Also submitted it upstream, hopefully it will be merged

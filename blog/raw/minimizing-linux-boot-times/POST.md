---
title: Minimizing Linux boot times
date: 2024-02-05
tags: firecracker, linux, optimization
slug: minimizing-linux-boot-times
description: Getting Linux to boot in 6ms
series: Boot time optimization
---

I recently read about [a project](https://www.usenix.org/publications/loginonline/freebsd-firecracker) to boot the FreeBSD kernel as fast as possible, and that made me wonder: How fast can you boot linux?


To get a baseline, I'm using [Firecracker](https://firecracker-microvm.github.io/), a very small VMM (virtual machine monitor) with their provided [example 5.10 kernel](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md#running-firecracker); this takes 1.037s to boot.

I started "bottom up"; by compiling my own kernel with `make tinylinux` and working up to a kernel that would boot.

I knew I only needed:
- Virtio Storage
- Virtio Network 
- EXT4 filesystem
- IP stack

And I _really_ wanted:
- 64 bit kernel
- TTY/Serial to see output
- Cgroups

With these options, I got a 1.6MB `bzImage`, which is about 10x smaller than the default Ubuntu kernel.

The testing environment consists of:
- My laptop (Ryzen 5 7640U, no tuning, kernel 6.2)
- A "default-sized" VM: 1 vCPU and 128MB RAM 
- A target kernel version 6.7.3
- Runtimes are measured by running every configuration 30 times and averaging

## Running an init program

To start, I built the most minimal C program which could show some signs of life

```c
#include <stdio.h>
int main() {
	printf("Hello!\n");
	return 4;
}
```

After running this as init, I got the exit code on the panic logs:
```
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000400
```
<smaller>_Aside: Why is the exit code shifted left?_</smaller>

but my `Hello!` message was nowhere to be found.

Reading the [firecracker docs](https://github.com/firecracker-microvm/firecracker/blob/main/docs/kernel-policy.md) I noticed that I also needed to enable `CONFIG_SERIAL_8250_CONSOLE`, and with that

```
[    0.004458] EXT4-fs (vda): write access unavailable, skipping orphan cleanup
Hello!
[    0.005957] Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000400
```

Success!

## Running a _cooler_ init program
As I don't really want to write my userspace applications in C, I wrote an equivalent program in Go:
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

But it really was not having any of this:
```
Kernel panic - not syncing: Requested init /goinit failed (error ENOEXEC).
```

The file itself had the executable bit set in the filesystem, so it must be something else; after enabling `CONFIG_IA32_EMULATION` I got a "way better" result:
```text
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
...
```

At least the runtime starts, though it's clearly unhappy, so I ran this program under a static build of `strace` (yes, `strace` as pid 1, we live in wild times!)

```
futex(0x815ba50, FUTEX_WAIT_PRIVATE, 0, NULL) = -1 ENOSYS (Function not implemented)
```

It turns out that the `futex` syscall is gated behind `CONFIG_COMPAT_32BIT_TIME`

After re-enabling `CONFIG_COMPAT_32BIT_TIME`, the Go program works

```text
[    0.004453] EXT4-fs (vda): write access unavailable, skipping orphan cleanup
Hello Go!
[    0.005732] Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000500
```

**Boot time: 35.2ms**.


### Talking to the outside world

A VM that can't talk to anything else is no fun, so we can set a [static IP configuration](https://docs.kernel.org/admin-guide/nfs/nfsroot.html) in the kernel command line by passing
```
ip=172.16.0.2::172.16.0.1:255.255.255.0:hostname:eth0:off
``` 

It's alive!
```text
$ bash start-vm.sh 
$ ping 172.16.0.2
PING 172.16.0.2 (172.16.0.2) 56(84) bytes of data.
64 bytes from 172.16.0.2: icmp_seq=1 ttl=64 time=0.508 ms
64 bytes from 172.16.0.2: icmp_seq=2 ttl=64 time=0.364 ms
64 bytes from 172.16.0.2: icmp_seq=3 ttl=64 time=0.299 ms
64 bytes from 172.16.0.2: icmp_seq=4 ttl=64 time=0.273 ms
```

**Boot time: 55.6ms**. Huh?! How could configuring a static IP take 20ms??

Looking at [kernel sources](https://github.com/torvalds/linux/blob/v6.7/net/ipv4/ipconfig.c#L1519) I found

```c
#define CONF_POST_OPEN 10
// ...
msleep(CONF_POST_OPEN);
```

right before the IP auto-configuration. I [made a patch](https://github.com/DavidVentura/fast-kernel-boot/blob/master/linux_sleep.patch) to disable this, and the regression went away.


**Boot time: 35.3ms**.

## Optimizing init time
### On core counts

It seems like boot time goes up by roughly 2.5ms per existing core:

<center>![](/images/minimizing-linux-boot-times/boot_time_vs_vcpu_count_smp.svg)</center>

What if we remove the handling of multiple cores altogether? By disabling SMP, the usable cores on a system is capped to 1, but that doesn't
matter for ther 1 vCPU / 128MB VM that we are benchmarking:

<center>![](/images/minimizing-linux-boot-times/boot_time_vs_vcpu_count_no_smp.svg)</center>

That's a **big** difference, I tried to dig into what's taking so long, but couldn't explain why the difference is so large, I found:
- 14ms from 2 `rcu_barrier` calls
  - one from `mark_rodata_ro`
  - one from `ipv4_offload_init`
- 1ms extra on `cpu_init`

I don't really know where the other ~12ms come from, but I'm not complaining about a free speedup.

**Boot time: 9.1ms**

### On memory sizes

The boot time goes up significantly when assigning more memory to the VM: 

<center>![](/images/minimizing-linux-boot-times/boot_time_vs_memory_size_4k.svg)</center>

As the only difference between these was the memory size, the time _must_ be getting spent setting up the kernel's page structures, which didn't make any sense to me.

This is the kernel code that's called in a loop to initialize the page structures:
```c
void __meminit __init_single_page(struct page *page, unsigned long pfn,
                                unsigned long zone, int nid)
{
        mm_zero_struct_page(page);
        set_page_links(page, zone, nid, pfn);
        init_page_count(page);
        page_mapcount_reset(page);
        page_cpupid_reset_last(page);
        page_kasan_tag_reset(page);

        INIT_LIST_HEAD(&page->lru);
#ifdef WANT_PAGE_VIRTUAL
        /* The shift won't overflow because ZONE_NORMAL is below 4G. */
        if (!is_highmem_idx(zone))
                set_page_address(page, __va(pfn << PAGE_SHIFT));
#endif
}
```

If I replaced this function with an empty stub, the bootup time remained flat, regardless of memory size (and the kernel immediately panic'd, which is reasonable).

As soon as _anything_ was done to `page`, the execution time shot back up, so this was not time spent processing, but triggered by merely accessing the memory.

Could it be page faulting on the host?

At this point I went to look at how Firecracker backs the guest's memory and it's [just a memory map](https://github.com/firecracker-microvm/firecracker/blob/4f19254474a296ecc1b78fd3444c303ac4922728/src/vmm/src/vstate/memory.rs#L185) but notably, these are the flags passed:

```rust
let prot = libc::PROT_READ | libc::PROT_WRITE;
let flags = if shared {
	libc::MAP_NORESERVE | libc::MAP_SHARED
} else {
	libc::MAP_NORESERVE | libc::MAP_PRIVATE
};
```

To validate my hypothesis about the delays being caused by page faults, I added `libc::MAP_POPULATE` to the flags.

This brought the boot time down by ~1ms at 128MB sizes, which confirms that we were spending some time page-faulting.

<center>![](/images/minimizing-linux-boot-times/boot_time_with_populate.svg)</center>

However.. the time to create the VM itself went up.. a lot:

<center>![](/images/minimizing-linux-boot-times/boot_and_vm_creation_populate.svg)</center>

This doesn't really help - while the kernel boot time goes down, the total time to launch the VM goes way up.

Luckily, there's another way to reduce page faults: using 2MB pages!

I made a [simple patch](https://github.com/DavidVentura/firecracker/commit/6f14487e4642fc7a369016edcea9935d6e547677) for Firecracker to allow specifying whether the VM's memory should be backed
by huge pages or not, and the boot time looks promising:

<center>![](/images/minimizing-linux-boot-times/boot_time_hugepages.svg)</center>

I looked at actual memory usage on a 128MB instance and only 11 hugepages were touched:

```bash
$ cat /sys/kernel/mm/hugepages/hugepages-2048kB/free_hugepages 
1024
$ bash start-vm.sh 
$ cat /sys/kernel/mm/hugepages/hugepages-2048kB/free_hugepages 
1013
```

This would've been _at most_ 5632 (2MB / 4KB \* 11 pages) page faults, which explains the ~3ms.

As a cherry on top, the time spent in the VMM went down, though I'm not sure why

<center>![](/images/minimizing-linux-boot-times/boot_and_vm_creation_hugepages.svg)</center>


**Boot time: 5.94ms**

### On the VMM time

Analyzing Firecracker is now interesting, as it _dominates_ the time to launch a VM.

Firecracker spends most of its time on the call to `kvm.create_vm()`, which weirdly takes a very variable amount of time, with some executions at ~0ms and some taking up to 40ms.

`kvm.create_vm()` is effectively just calling `ioctl(18, KVM_CREATE_VM, 0)` and `strace` confirms that this ioctl randomly takes 20~40ms 

The distribution of the duration of these calls is just _weird_:

<center>![](/images/minimizing-linux-boot-times/vmm_creation_variance.svg)</center>

When looking up `KVM_CREATE_VM slow`, I found [this](https://github.com/firecracker-microvm/firecracker/issues/2129) Firecracker issue, which led me to [this](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md#linux-61-boot-time-regressions) documentation page; which suggests mounting cgroups with the `favordynmods` flags.

When applying the flag, the duration of the `ioctl` calls goes down consistently:

<center>![](/images/minimizing-linux-boot-times/boot_and_vm_creation_cgroups_hugepages.svg)</center>


**Final boot time: 6.0ms**

**Final boot time (with VM Creation): 8.9ms**

## Other

I didn't really know of any tools to measure boot times precisely, I'd have loved to somehow get a flamegraph of where time is being spent during boot (and early boot!). All of the analysis I did on these was basically achieved by placing prints and measuring time it took to get to them.

The scripts used to run, measure & graph the VM startup times live in the [Github repo](https://github.com/DavidVentura/blog/tree/master/blog/raw/minimizing-linux-boot-times), along with the data used to generate them.

Boot time is measured with Firecracker's `--boot-timer` option; this option attaches an MMIO device, so that userland programs can communicate when they start, by writing to a specific address (`0xd0000000`).

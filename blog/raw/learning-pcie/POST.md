---
title: Learning about PCI-e: Emulating a custom device
date: 2024-05-06
tags: qemu, c, pci-gpu
slug: learning-pcie
description: Creating a very simple PCI-e device in QEMU
series: Learning about PCI-e
---

Ever since reading about the [FuryGpu](https://www.furygpu.com/), I've been curious about how PCI-e works and what it would take to build a simple display adapter.
In this post I will try to document what I learn during the process.

Thsi project is probably way larger than I can even imagine, so I'm going to try an iterative process, taking the smallest steps that further my understanding and can achieve _something_.

My current, _limited_, understanding of PCI-e:

When you plug an adapter (card) into a PCI-e slot, *magic happens* then:

1. The card becomes enumerable in the PCI-e bus by the kernel
2. The kernel loads a driver based on the vendor/device code exposed by the card.
3. The driver knows how to communicate with the card (writing/reading specific memory offsets)

A good first step to further my understanding: "build" a "device" that can be enumerated by Linux, and read/write to it.

As an example, my graphics card currently enumerates like this:

```sh
c1:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Phoenix1 (rev cb) (prog-if 00 [VGA controller])
        Subsystem: Device f111:0006
        Control: I/O+ Mem+ BusMaster+ SpecCycle- MemWINV- VGASnoop- ParErr- Stepping- SERR- FastB2B- DisINTx+
        Status: Cap+ 66MHz- UDF- FastB2B- ParErr- DEVSEL=fast >TAbort- <TAbort- <MAbort- >SERR- <PERR- INTx-
        Latency: 0, Cache Line Size: 64 bytes
        Interrupt: pin A routed to IRQ 81
        IOMMU group: 4
        Region 0: Memory at 8000000000 (64-bit, prefetchable) [size=256M]
        Region 2: Memory at 90000000 (64-bit, prefetchable) [size=2M]
        Region 4: I/O ports at 1000 [size=256]
        Region 5: Memory at 90500000 (32-bit, non-prefetchable) [size=512K]
        Capabilities: <access denied>
        Kernel driver in use: amdgpu
        Kernel modules: amdgpu
```

Building a real device at my current level of understanding would be _slightly insane_, so I'm going to emulate one in [QEMU](https://www.qemu.org/).

## QEMU

Adding a new device to QEMU's source requires us to be able to build it, which is straightforward:

```bash
$ ./configure --target-list="x86_64-softmmu" --enable-debug
$ make -j8
```

The resulting binary can then be executed with `./build/qemu-system-x86_64`.

To validate that the binary works, I copied my laptop's kernel `cp -t . /boot/vmlinuz`:

```sh
$ ./build/qemu-system-x86_64 -kernel vmlinuz \
	-display none -m 256 \
	-chardev stdio,id=char0 -serial chardev:char0 \
	-append 'console=ttyS0 quiet panic=-1'
[    3.232653] Initramfs unpacking failed: write error
[    3.882868] Failed to execute /init (error -2)
[    3.885107] Kernel panic - not syncing: No working init found.  Try passing init= option to kernel. See Linux Documentation/admin-guide/init.rst for guidance.
[    3.885863] CPU: 0 PID: 1 Comm: swapper/0 Not tainted 6.2.0-39-generic #40-Ubuntu
[    3.886198] Hardware name: QEMU Standard PC (i440FX + PIIX, 1996), BIOS rel-1.16.3-0-ga6ed6b701f0a-prebuilt.qemu.org 04/01/2014
```

This error is expected - without a disk attached to the VM, there's no `/init` to execute.

The easiest way to execute some code is to package it up in an initramfs, in [cpio format](https://www.kernel.org/doc/html/v4.14/admin-guide/initrd.html#compressed-cpio-images).

To build a basic initramfs:

1. Download [static busybox](https://www.busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox) and place it into a dir called `initramfs`
2. Write this init script as `initramfs/init.sh` and make it executable
```sh
#!/busybox sh
/busybox mkdir /sys
/busybox mkdir /proc
/busybox mount -t proc null /proc
/busybox mount -t sysfs null /sys
/busybox mknod /dev/mem c 1 1
/busybox lspci
exec /busybox sh
```
3. Create a CPIO archive `cd initramfs && find . -print0 | cpio --null -H newc -o | gzip -9 > ../initramfs.gz`


We can pass this `initramfs.gz` file to the kernel to be executed (also note `rdinit` in the kernel's arguments):

```sh
$ ./build/qemu-system-x86_64 -enable-kvm -kernel vmlinuz -initrd initramfs.gz \
	-chardev stdio,id=char0 -serial chardev:char0 \
	-append 'quiet console=ttyS0,115200 rdinit=/init.sh' \
	-display none -m 256  -nodefaults
00:01.0 Class 0601: 8086:7000
00:00.0 Class 0600: 8086:1237
00:01.3 Class 0680: 8086:7113
00:01.1 Class 0101: 8086:7010
```

This shows that we can execute some arbitrary commands, and tha there are 4 devices in the PCI bus on an otherwise "empty" virtual machine.

From this point on I'll refer to these QEMU commandline options as `$OPTS`

## Creating a _very minimal_ device

To create a PCI-e device in QEMU, we only need to provide a few things:

* A state definition (as a struct)
* A function to register our device
* Init/realize functions

We can create a `gpu.c` file in `hw/misc` (slightly abbreviated, find the file in [the Github repo](https://github.com/DavidVentura/blog/tree/master/blog/raw/learning-pcie/minimal-listing.c)):
```c
#define TYPE_PCI_GPU_DEVICE "gpu"
#define GPU_DEVICE_ID 		0x1337

static void pci_gpu_register_types(void) {
    static InterfaceInfo interfaces[] = {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    };
    static const TypeInfo gpu_info = {
        .name          = TYPE_PCI_GPU_DEVICE,
        .parent        = TYPE_PCI_DEVICE,
        .instance_size = sizeof(GpuState),
        .instance_init = gpu_instance_init,
        .class_init    = gpu_class_init,
        .interfaces = interfaces,
    };

    type_register_static(&gpu_info);
}

static void gpu_class_init(ObjectClass *class, void *data) {
    PCIDeviceClass *k = PCI_DEVICE_CLASS(class);

    k->realize = pci_gpu_realize;
    k->exit = pci_gpu_uninit;
    k->vendor_id = PCI_VENDOR_ID_QEMU;
    k->device_id = GPU_DEVICE_ID;
    k->class_id = PCI_CLASS_OTHERS;
}
```

We also need to update the build system to build this device:

```diff
$ git diff hw
diff --git a/hw/misc/Kconfig b/hw/misc/Kconfig
index 1e08785..a2e533e 100644
--- a/hw/misc/Kconfig
+++ b/hw/misc/Kconfig
@@ -25,6 +25,11 @@ config PCI_TESTDEV
     default y if TEST_DEVICES
     depends on PCI

+config GPU
+    bool
+    default y if TEST_DEVICES
+    depends on PCI && MSI_NONBROKEN
+
 config EDU
     bool
     default y if TEST_DEVICES
diff --git a/hw/misc/meson.build b/hw/misc/meson.build
index 86596a3..ca704f4 100644
--- a/hw/misc/meson.build
+++ b/hw/misc/meson.build
@@ -1,4 +1,6 @@
 system_ss.add(when: 'CONFIG_APPLESMC', if_true: files('applesmc.c'))
+system_ss.add(when: 'CONFIG_GPU', if_true: files('gpu.c'))
 system_ss.add(when: 'CONFIG_EDU', if_true: files('edu.c'))
 system_ss.add(when: 'CONFIG_FW_CFG_DMA', if_true: files('vmcoreinfo.c'))
 system_ss.add(when: 'CONFIG_ISA_DEBUG', if_true: files('debugexit.c'))
```

We can then rebuild QEMU with `make` (this time it's super quick) and run
```bash
$ ./build/qemu-system-x86_64 $OPTS -device gpu
00:01.0 Class 0601: 8086:7000
00:04.0 Class 00ff: 1234:1337 # <<<< our device
00:00.0 Class 0600: 8086:1237
00:01.3 Class 0680: 8086:7113
00:03.0 Class 0200: 8086:100e
00:01.1 Class 0101: 8086:7010

```

At this point, I also built [lspci](https://github.com/pciutils/pciutils/tree/master) statically (add `-static` to OPTS and set `HWDB` to `no`) and put it in the initramfs, for a more complete `lspci` output, which gave me:

```
00:04.0 Class [00ff]: Device [1234:1337]
        Subsystem: Device [1af4:1100]
        Physical Slot: 4
        Control: I/O+ Mem+ BusMaster- SpecCycle- MemWINV- VGASnoop- ParErr- Stepping- SERR+ FastB2B- DisINTx-
        Status: Cap- 66MHz- UDF- FastB2B- ParErr- DEVSEL=fast >TAbort- <TAbort- <MAbort- >SERR- <PERR- INTx-
```

## Doing _something_ with the device

At this point, the 'GPU' does absolutely nothing, other than showing up on the bus.

To advertise a memory region to the CPU, it needs to be visible in the card's [configuration space](https://en.wikipedia.org/wiki/PCI_configuration_space), we can do this by 
configuring a {^BAR|base address register}, which will contain a base address and size for the memory region.

First, define the memory region and create some memory to operate on
```diff
  struct GpuState {
      PCIDevice pdev;
+     MemoryRegion mem;
+     unsigned char data[0x100000];
  };
```

Then when the device is instantiated (realized), we need to register the memory region & tell QEMU what to do with read/write operations (find the file in [the Github repo](https://github.com/DavidVentura/blog/tree/master/blog/raw/learning-pcie/02-with-memory-region.c)):

```c
static uint64_t gpu_mem_read(void *opaque, hwaddr addr, unsigned size) {
  GpuState *gpu = opaque;
  uint64_t bitcount = ((uint64_t)size)<<3;
  uint64_t mask = (1ULL << bitcount)-1;
  uint64_t got = gpu->data[addr] & mask;
  printf("Tried to read 0x%x bytes at 0x%lx = 0x%lx\n", size, addr, got);
  return got;
}
static void gpu_mem_write(void *opaque, hwaddr addr, uint64_t val, unsigned size) {
  GpuState *gpu = opaque;
  uint64_t bitcount = ((uint64_t)size)<<3;
  uint64_t mask = (1ULL << bitcount)-1;
  uint64_t sizedval = val & mask;
  gpu->data[addr] = sizedval;
  printf("Tried to write 0x%lx [0x%lx] (0x%x bytes) at 0x%lx\n", val, sizedval, size, addr);
}
static const MemoryRegionOps gpu_mem_ops = {
  .read = gpu_mem_read,
  .write = gpu_mem_write,
};
static void pci_gpu_realize(PCIDevice *pdev, Error **errp)
{
  GpuState *gpu = GPU(pdev);
  memory_region_init_io(&gpu->mem, OBJECT(gpu), &gpu_mem_ops, gpu, "gpu-mem", 1 * MiB);
  pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &gpu->mem);
}
```

The new memory region shows up in `lspci`!
```bash
00:02.0 Class [00ff]: Device [1234:1337]
        Subsystem: Device [1af4:1100]
        Physical Slot: 2
        Control: I/O+ Mem+ BusMaster- SpecCycle- MemWINV- VGASnoop- ParErr- Stepping- SERR+ FastB2B- DisINTx-
        Status: Cap- 66MHz- UDF- FastB2B- ParErr- DEVSEL=fast >TAbort- <TAbort- <MAbort- >SERR- <PERR- INTx-
        Region 0: Memory at feb00000 (32-bit, non-prefetchable) [size=1M] <<<<< here
```

Now we have 1 memory region, which is 32-bit-addressable and 1MB large, and it can be interacted by reading/writing to it

```bash
$ /busybox mknod /dev/mem c 1 1     # create /dev/mem to be able read/write arbitrary memory
$ /busybox devmem 0xfeb00000 16 	# read 4 bytes
0x0000
$ /busybox devmem 0xfeb00000 16 4 	# write a '4', as a 4 byte type
$ /busybox devmem 0xfeb00000 16 	# read 4 bytes
0x0004
```
And QEMU logged
```bash
Tried to read 0x2 bytes at 0x0 = 0x0
Tried to write 0x4 [0x4] (0x2 bytes) at 0x0
Tried to read 0x2 bytes at 0x0 = 0x4
```

If we wanted to have multiple memory regions, we'd need to duplicate: `gpu_mem_read`, `gpu_mem_write`, `gpu_mem_ops`, then call `memory_region_init` and `pci_register_bar` with those parameters.


That's it for now, [next time](/pcie-driver-dma.html) we are tackling DMA & a simple kernel driver.

## References

1. [Down to the TLP: How PCI express devices talk (Part I)](https://xillybus.com/tutorials/pci-express-tlp-pcie-primer-tutorial-guide-1)
2. [pciemu](https://github.com/luizinhosuraty/pciemu)
3. [implementation of a custom QEMU PCI device](https://www.linkedin.com/pulse/implementing-custom-qemu-pci-device-nikos-mouzakitis)
4. [How the PCI Express Protocol works (Video)](https://www.youtube.com/watch?v=sRx2YLzBIqk)
5. [QEMU's EDU device](https://www.qemu.org/docs/master/specs/edu.html)
6. [QEMU PCI slave devices](https://airbus-seclab.github.io/qemu_blog/pci_slave.html)
7. [QEMU: How to Design a Prototype Device](https://milokim.gitbooks.io/lbb/content/qemu-how-to-design-a-prototype-device.html)
8. [Writing a custom device for QEMU](https://sebastienbourdelin.com/2021/06/16/writing-a-custom-device-for-qemu/)
9. [QEMU internal PCI device](https://dangokyo.me/2018/03/28/qemu-internal-pci-device/)

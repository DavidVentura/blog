---
title: Learning about PCI-e: Emulating a custom device
date: 2024-05-06
tags: pci-e, qemu, c
slug: learning-pcie
incomplete: true
description: Creating a PCI-e device in QEMU that Linux can enumerate
---

Ever since reading about the [FuryGpu](https://www.furygpu.com/), I've been curious about how PCI-e works and what it would take to build a simple display adapter.
In this post I will try to document what I learn during the process.

Thsi project is probably way larger than I can imagine, so I'm going to try an iterative process, taking the smallest steps that further my understanding and can achieve _something_.

My current, _limited_, understanding of PCI-e:

When you plug an adapter (card) into a PCI-e slot, *magic happens* and it will be enumerable in the PCI-e bus by the kernel.
The kernel can then load a driver based on the vendor/device code exposed by the card.
The driver knows how to communicate with the card, can share memory and send/receive commands.

A good step to understand _a lot more_: build a device that's able to be enumerated by Linux.

As an example, my graphics card currently enumerates like this:

```
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

As building a real device right now would be _slightly insane_, I'm going to emulate one in QEMU.

## QEMU

```bash
./configure --target-list="x86_64-softmmu" --enable-debug
make -j8
```
`./build/qemu-system-x86_64`
yoink own kernel & initrd: cp -t . /boot/initrd.img /boot/vmlinuz

Should be able to validate it works:

```
$ ./build/qemu-system-x86_64  -kernel vmlinuz -initrd initrd.img  -chardev stdio,id=char0 -serial chardev:char0 -append 'console=ttyS0 quiet' -display none -m 256
[    3.232653] Initramfs unpacking failed: write error
[    3.882868] Failed to execute /init (error -2)
[    3.885107] Kernel panic - not syncing: No working init found.  Try passing init= option to kernel. See Linux Documentation/admin-guide/init.rst for guidance.
[    3.885863] CPU: 0 PID: 1 Comm: swapper/0 Not tainted 6.2.0-39-generic #40-Ubuntu
[    3.886198] Hardware name: QEMU Standard PC (i440FX + PIIX, 1996), BIOS rel-1.16.3-0-ga6ed6b701f0a-prebuilt.qemu.org 04/01/2014
```
### Adding a new device

copy edu.c to enumerate.c
rename + change device id

```diff
$ git diff hw
diff --git a/hw/misc/Kconfig b/hw/misc/Kconfig
index 1e08785..a2e533e 100644
--- a/hw/misc/Kconfig
+++ b/hw/misc/Kconfig
@@ -25,6 +25,11 @@ config PCI_TESTDEV
     default y if TEST_DEVICES
     depends on PCI
 
+config ENUMERATE
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
+system_ss.add(when: 'CONFIG_ENUMERATE', if_true: files('enumerate.c'))
 system_ss.add(when: 'CONFIG_EDU', if_true: files('edu.c'))
 system_ss.add(when: 'CONFIG_FW_CFG_DMA', if_true: files('vmcoreinfo.c'))
 system_ss.add(when: 'CONFIG_ISA_DEBUG', if_true: files('debugexit.c'))
```

```bash
$ ./build/qemu-system-x86_64 -enable-kvm -device enumerate -kernel vmlinuz -initrd initrd.img  -chardev stdio,id=char0 -serial chardev:char0 -append 'console=ttyS0 quiet' -display none -m 256
```

we added `-device enumerate` and qemu did not refuse it.


### Listing a new device

Build initramfs:

1. download [static busybox](https://www.busybox.net/downloads/binaries/1.35.0-x86_64-linux-musl/busybox) and place it into a dir called `initramfs`
2. write this init script
```sh
#!/busybox sh
/busybox mkdir /sys
/busybox mkdir /proc
/busybox mount -t proc null /proc
/busybox mount -t sysfs null /sys
/busybox lspci
exec /busybox sh
```
3. [create a cpio](https://www.kernel.org/doc/html/v4.14/admin-guide/initrd.html#compressed-cpio-images) `cd initramfs && find . -print0 | cpio --null -H newc -o | gzip -9 > ../initramfs.gz`

when running a vm now
```
$ ./build/qemu-system-x86_64 -enable-kvm  -kernel vmlinuz -initrd  initramfs.gz  -chardev stdio,id=char0 -serial chardev:char0 -append 'quiet console=ttyS0,115200 rdinit=/init.sh' -display none -m 256  -device enumerate -nodefaults
00:01.0 Class 0601: 8086:7000
00:00.0 Class 0600: 8086:1237
00:01.3 Class 0680: 8086:7113
00:01.1 Class 0101: 8086:7010
00:02.0 Class 00ff: 1234:1337
#                   ^^^^^^^^^ the 'enumerate' device
```
## Enumerating

## References

1. [Down to the TLP: How PCI express devices talk (Part I)](https://xillybus.com/tutorials/pci-express-tlp-pcie-primer-tutorial-guide-1)
2. [pciemu](https://github.com/luizinhosuraty/pciemu)
3. [implementation of a custom QEMU PCI device](https://www.linkedin.com/pulse/implementing-custom-qemu-pci-device-nikos-mouzakitis)
4. [How the PCI Express Protocol works [Video]](https://www.youtube.com/watch?v=sRx2YLzBIqk)
5. [QEMU's EDU device](https://www.qemu.org/docs/master/specs/edu.html)
6. [QEMU PCI slave devices](https://airbus-seclab.github.io/qemu_blog/pci_slave.html)

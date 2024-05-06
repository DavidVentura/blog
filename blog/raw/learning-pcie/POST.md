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

## Enumerating

## References

1. [Down to the TLP: How PCI express devices talk (Part I)](https://xillybus.com/tutorials/pci-express-tlp-pcie-primer-tutorial-guide-1)
2. [pciemu](https://github.com/luizinhosuraty/pciemu)
3. [implementation of a custom QEMU PCI device](https://www.linkedin.com/pulse/implementing-custom-qemu-pci-device-nikos-mouzakitis)
4. [How the PCI Express Protocol works [Video]](https://www.youtube.com/watch?v=sRx2YLzBIqk)
5. [QEMU's EDU device](https://www.qemu.org/docs/master/specs/edu.html)

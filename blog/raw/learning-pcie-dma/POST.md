---
title: Learning about PCI-e: Writing a kernel driver
date: 2024-05-11
tags: pci-e, qemu, c
slug: pcie-driver
ddeviceescription: Creating a very simple driver for a simple PCI-e device (in QEMU)
---


In the [previous entry](/learning-pcie.html) we covered the implementation of a trivial PCI-e device, which allowed us to read and write to it, 32 bits at a time.

Instead of relying on manual peek/poke, we should work on talking to the device in a more structured way, through a [character device]().

Before, we were running `devmem 0xfeb00000` and `0xfeb00000` came from copy-pasting the address of BAR0, which we got from running `lspci`.

Now, we need to get this address in a programmatic fashion:

- Register a PCI driver
- Probe
	- get available BAR ids
	- get BAR addr + len


## Initializing the adapter

make a [pci_driver](https://elixir.bootlin.com/linux/v6.9/source/include/linux/pci.h#L887) struct, which requires two fields:

A table of supported devices, by device/vendor ID:

```c
static struct pci_device_id gpu_id_tbl[] = {
	{ PCI_DEVICE(0x1234, 0x1337) },
	{ 0, },
};
```

and a `probe` function (which is only called if the device/vendor IDs match), that needs to return `0` if it takes ownership of the device.

Within the `probe` function, we can enable the device and store a reference to the `pci_dev`:

```c
static int gpu_probe(struct pci_dev *pdev, const struct pci_device_id *id) {
	int bars;
	int err;
	unsigned long mmio_start, mmio_len;
	GpuState* gpu = kmalloc(sizeof(struct GpuState), GFP_KERNEL);
	gpu->pdev = pdev;
	pr_info("called probe");

	pci_enable_device_mem(pdev);

	// create a bitfield of the available BARs
	bars = pci_select_bars(pdev, IORESOURCE_MEM);

	// claim ownership of the address space for each BAR in the bitfield
	pci_request_region(pdev, bars, "gpu-pci");

	mmio_start = pci_resource_start(pdev, 0);
	mmio_len = pci_resource_len(pdev, 0);

	// map physical address to virtual
	gpu->hwmem = ioremap(mmio_start, mmio_len);
	pr_info("mmio starts at 0x%lx; hwmem 0x%px", mmio_start, gpu->hwmem);
	return 0;
}
```

Now, if we call [pci_register_driver]() during `module_init`, we can see it's being called:
```
[    0.488699] called probe
[    0.488705] mmio starts at 0xfe000000; hwmem 0xffffbf5200600000
[    0.488817] gpu_module_init done
```

## Accessing the adapter via a character device

what is chardev:

char dev: exposes open/read/write (and more)

smuggle BAR idx via MINOR device nr

smuggling via container_of
https://linux-kernel-labs.github.io/refs/heads/master/labs/device_drivers.html#implementation-of-operations


## Multiple memory regions
- add second buffer
        Region 0: Memory at fe000000 (32-bit, non-prefetchable) [size=1M]
        Region 1: Memory at fd000000 (32-bit, non-prefetchable) [size=16M]


- second chardev for fb with forwarding read/write in a loop

## DMA

This is great, but it's not very practical for large data transfers - sending 1 packet a time will keep the CPU busy.

Instead, we ask the card to take care of copying the data itself, by using {^DMA|Direct Memory Access}, for which:
2. The CPU has to tell the card what data to copy (source address, length) and to where (destination address)
3. The CPU has to tell the card when it is ready for the copy to start
4. The adapter has to tell the CPU when it has finished the transfer
	1. IRQ = The adapter needs to be granted the [Bus Master](https://en.wikipedia.org/wiki/Bus_mastering) capability

after msi_init in QEMU
        Capabilities: [40] MSI: Enable- Count=1/1 Maskable- 64bit+
                Address: 0000000000000000  Data: 0000

kernel request_irq
```
/ # cat /proc/interrupts 
           CPU0       
  ...
 24:          0  PCI-MSI-0000:00:02.0   0-edge      GPU
```

the interrupt does not work -> requires DMA & bus mastering, makes sense, an MSI is a Message-Signaled-Interrupt AKA a normal packet sent by the card via DMA

irq threading
```
   98 0         0:00 [irq/24-GPU-Dma0]
   99 0         0:00 [irq/25-GPU-Test]
```

- DMA
	-> no completion notif
	-> interrupt for completion

after read/write is done:
- display fb in qemu

later:
- locking the dma engine(s)?
- how to have multiple writes in flight?

enabling MSI (lspci adds)

```
Capabilities: [40] MSI: Enable- Count=1/4 Maskable- 64bit+                                             
		Address: 0000000000000000  Data: 0000
```

on qemu, init msi:
`msi_init`

1- handle request DMA
2- raise IRQ when done
	a- this never goes back on its own
3- handle "ACK-irq"
	a- lower IRQ when received


## References:

1. [Kernel's docs on PCI](https://www.kernel.org/doc/Documentation/PCI/pci.txt)
1. [Kernel's docs on MSI](https://www.kernel.org/doc/Documentation/PCI/MSI-HOWTO.txt)
1. [Linux Kernel Labs - Device Drivers](https://linux-kernel-labs.github.io/refs/heads/master/labs/device_drivers.html)
1. [Writing a PCI device driver for Linux](https://olegkutkov.me/2021/01/07/writing-a-pci-device-driver-for-linux/)
1. [Simple character device driver for Linux](https://olegkutkov.me/2018/03/14/simple-linux-character-device-driver/)
1. [pciemu](https://github.com/luizinhosuraty/pciemu)

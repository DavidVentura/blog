---
title: Learning about PCI-e: Driver & DMA
date: 2024-05-25
tags: pci-e, qemu, c
slug: pcie-driver-dma
description: Creating a simple driver for a simple PCI-e device (in QEMU)
incomplete: yes
---


In the [previous entry](/learning-pcie.html) we covered the implementation of a trivial PCI-e device, which allowed us to read and write to it, 32 bits at a time, 
by relying on manual peek/poke with a hardcoded address (`0xfe000000`) which came from copy-pasting the address of BAR0 from `lspci`.

To get this address programmatically, we need to ask the PCI subsystem for the details of the memory mapping for this device.

First, we need to make a [struct pci_driver](https://elixir.bootlin.com/linux/v6.9/source/include/linux/pci.h#L887), which only requires two fields: a table of supported devices, and a `probe` function.

The table of supported devices is an array of the pairs of device/vendor IDs which this driver supports:

```c
static struct pci_device_id gpu_id_tbl[] = {
	{ PCI_DEVICE(0x1234, 0x1337) },
	{ 0, },
};
```

The `probe` function (which is only called if the device/vendor IDs match), needs to return `0` if it takes ownership of the device.

We need to update the driver's state to hold a reference to the device's memory region

```diff
 typedef struct GpuState {
 	struct pci_dev *pdev;
+	u8 __iomem *hwmem;
 } GpuState;
```

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

	// create a bitfield of the available BARs, eg: 0b1 for 'BAR #0'
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


Now, if we call `pci_register_driver` during `module_init`, we can see the card is initialized and we get back the BAR0 address:

```bash
[    0.488699] called probe
[    0.488705] mmio starts at 0xfe000000; hwmem 0xffffbf5200600000
[    0.488817] gpu_module_init done
```

## Accessing the adapter via a character device

Now that we have mapped the BAR0 address space in our kernel driver, we can expose a nicer interface for users: a character device, which allows direct, unbuffered access to the device they represent.

For this driver, we only need to implement `open`, `read` and `write`, which have these signatures:

```c
static int gpu_open(struct inode *inode, struct file *file);
static ssize_t gpu_read(struct file *file, char __user *buf, size_t count, loff_t *offset);
static ssize_t gpu_write(struct file *file, const char __user *buf, size_t count, loff_t *offset);
```

First, add a reference to the cdev in the driver's state
```diff
 typedef struct GpuState {
 	struct pci_dev *pdev;
 	u8 __iomem *hwmem;
+	struct cdev cdev;
 } GpuState;
```

Then we define a set of file operations and a `setup` function:

```c
static const struct file_operations fileops = {
	.owner 		= THIS_MODULE,
	.open 		= NULL,
	.read 		= NULL,
	.write 		= NULL
};

int setup_chardev(GpuState* gpu, struct class* class, struct pci_dev *pdev) {
	dev_t dev_num, major;
	alloc_chrdev_region(&dev_num, 0, MAX_CHAR_DEVICES, "gpu-chardev");
	major = MAJOR(dev_num);

	cdev_init(&gpu->cdev, &fileops);
	cdev_add(&gpu->cdev, MKDEV(major, 0), 1);
	device_create(class, NULL, MKDEV(major, 0), NULL, "gpu-io");
	return 0;
}
```

At this point, the character device will be visible in the filesystem:

```bash
/ # ls -l /dev/gpu-io 
crw-rw----    1 0        0         241,   0 May 25 15:58 /dev/gpu-io
```

At this point, I tried to `write` and got a bit stuck, as `write` receives a `void* private_data` via the `struct file*` but it must be populated during `open`, which does _not_ receive a `private_data`/`user_data` argument.

When reading the definition of [struct inode](https://elixir.bootlin.com/linux/latest/source/include/linux/fs.h#L721), I saw a pointer back to the character device (`struct cdev *i_cdev`), which gave me an idea:

As `struct GpuState` _embeds_ `struct cdev`, having a pointer to `struct cdev` allows us to get a reference back to `GpuState` with `offset_of`:

<img src="/images/pcie-device/container_of.svg" style="margin: 0px auto; width: 100%; max-width: 40rem" />

The kernel provides a `container_of` macro which is built for this specific purpose, so we can now implement open/read/write:

```c
static int gpu_open(struct inode *inode, struct file *file) {
	GpuState *gpu = container_of(inode->i_cdev, struct GpuState, cdev);
	file->private_data = gpu;
	return 0;
}
```

and read/write are simple "one dword at a time" implementations:
```c
static ssize_t gpu_read(struct file *file, char __user *buf, size_t count, loff_t *offset) {
	GpuState *gpu = (GpuState*) file->private_data;
	uint32_t read_val = ioread32(gpu->hwmem + *offset);
	copy_to_user(buf, &read_val, 4);
	*offset += 4;
	return 4;
}
static ssize_t gpu_write(struct file *file, const char __user *buf, size_t count, loff_t *offset) {
	GpuState *gpu = (GpuState*) file->private_data;
	u32 n;
	copy_from_user(&n, buf + *offset + written, 4);
	*offset += 4;
	return 4;
}
```

This works great! Sadly, it's not a practical implementation for large data transfers - sending 1 packet a time will keep the CPU busy and take a long time: it took ~800ms to transfer 1.2MiB (640x480x32bpp)!

## DMA

Instead of copying one dword at a time, we can ask the card to take care of copying the data itself, by using {^DMA|Direct Memory Access}, for which:

1. The CPU has to tell the card what data to copy (source address, length) and to where (destination address)
2. The CPU has to tell the card when it is ready for the copy to start
3. The card has to tell the CPU when it has finished the transfer
	1. IRQ = The adapter needs to be granted the [Bus Master](https://en.wikipedia.org/wiki/Bus_mastering) capability

To send commands to the card, we can use [memory-mapped IO](https://en.wikipedia.org/wiki/Memory-mapped_I/O_and_port-mapped_I/O): we treat certain memory addresses as registers: some registers will be the 'parameters' to our 'function call', and writing to a specific register will trigger the execution of the 'function call'.

As an example, we can map these addresses as registers:

```c
#define REG_DMA_DIR 		0
#define REG_DMA_ADDR_SRC 	1
#define REG_DMA_ADDR_DST 	2
#define REG_DMA_LEN 		3
#define REG_DMA_START 		4
```

and implement a function to execute DMA:
```c
static void write_reg(GpuState* gpu, u32 val, u32 reg) {
	iowrite32(val, 	gpu->hwmem + (reg * sizeof(u32)));
}
void execute_dma(GpuState* gpu, u8 dir, u32 src, u32 dst, u32 len) {
	write_reg(gpu, dir, REG_DMA_DIR);
	write_reg(gpu, src,	REG_DMA_ADDR_SRC);
	write_reg(gpu, dst,	REG_DMA_ADDR_DST);
	write_reg(gpu, len,	REG_DMA_LEN);
	write_reg(gpu, 1, 	REG_DMA_START);
}
```

We also need to implement the MMIO side in the adapter:
```c
static void gpu_control_write(void *opaque, hwaddr addr, uint64_t val, unsigned size) {
	GpuState *gpu = opaque;
	val = lower_n_bytes(val, size);
	uint32_t reg = addr / 4;
	switch (reg) {
		case REG_DMA_DIR:
		case REG_DMA_ADDR_SRC:
		case REG_DMA_ADDR_DST:
		case REG_DMA_LEN:
			gpu->registers[reg] = (uint32_t)val;
			break;
		case REG_DMA_START:
			if (gpu->registers[REG_DMA_DIR] == DIR_HOST_TO_GPU) {
				pci_dma_read(&gpu->pdev,
							 gpu->registers[REG_DMA_ADDR_SRC], // host addr
							 (gpu->framebuffer + gpu->registers[REG_DMA_ADDR_DST]), // dev addr
							 gpu->registers[REG_DMA_LEN]);
			} else {
				printf("Unimplemented DMA direction\n");
			}
			break;
	}
}
```
in which we only store the 'arguments' to the DMA 'function call', and execute it when a token value is written.

Then, we can go back to the kernel driver and implement `write`:

```c
static ssize_t gpu_fb_write(struct file *file, const char __user *buf, size_t count, loff_t *offset) {
	GpuState *gpu = (GpuState*) file->private_data;
	dma_addr_t dma_addr;
	u8* kbuf = kmalloc(count, GFP_KERNEL);
	copy_from_user(kbuf, buf, count);

	dma_addr = dma_map_single(&gpu->pdev->dev, kbuf, count, DMA_TO_DEVICE);
	execute_dma(gpu, DIR_HOST_TO_GPU, dma_addr, *offset, count);
	kfree(kbuf);
	return count;
}
```

Which now is fast enough to report as ~300us on my system. We may revisit later to go for a zero-copy implementation.

There's a problem though; the DMA execution is asynchronous, and it would be a lot nicer if `write` would block until the write has finished.

## Interrupts

Interrupts are a way for devices to signal to the CPU that some event has happened; we can use one to signify that the DMA transfer has completed.

First, we define some shared constants

```c
#define IRQ_COUNT 			1
#define IRQ_DMA_DONE_NR 	0
```

In qemu, in `pci_gpu_realize` we need to add
```c
msix_init(pdev, IRQ_COUNT, &gpu->mem, 0 /* table_bar_nr  = bar id */, 0x1000 /* table_offset */,
		  &gpu->mem, 0 /* pba_bar_nr  = bar id */, 0x3000 /* pba_offset */, 0x0 /* capabilities */, errp);
for(int i = 0; i < IRQ_COUNT; i++)
	msix_vector_use(pdev, i);
```

which will reserve an 8KiB space for MSIs (at the 4K offset) and another 8KiB space for PBAs at the 12KiB offset.

Then to send an interrupt when `pci_dma_read` finishes, we can call

```c
msix_notify(&gpu->pdev, IRQ_DMA_DONE_NR);
```

The kernel needs to hook a handler for the interrupt, which can be done with

```c
static irqreturn_t irq_handler(int irq, void *data) {
	pr_info("IRQ %d received\n", irq);
	return IRQ_HANDLED;
}
static int setup_msi(GpuState* gpu) {
	int msi_vecs;
	int irq_num;

	msi_vecs = pci_alloc_irq_vectors(gpu->pdev, IRQ_COUNT, IRQ_COUNT, PCI_IRQ_MSIX | PCI_IRQ_MSI);
	irq_num = pci_irq_vector(gpu->pdev, IRQ_DMA_DONE_NR);
	pr_info("Got MSI vec %d, IRQ num %d", msi_vecs, irq_num);
	request_threaded_irq(irq_num, irq_handler, NULL, 0, "GPU-Dma0", gpu);
	return 0;
}
```

and we can call `setup_msi` in the `gpu_probe` (PCI probe) function.

On boot, we can see these changes reflected in the device:

```bash
/ # lspci -vv
...
Region 0: Memory at fc000000 (32-bit, non-prefetchable) [size=16M]
Capabilities: [40] MSI-X: Enable- Count=1 Masked-
        Vector table: BAR=0 offset=00001000
        PBA: BAR=0 offset=00003000
...
/ # cat /proc/interrupts 
           CPU0       
  ...
 24:          0  PCI-MSI-0000:00:02.0   0-edge      GPU
```


kernel request_irq

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

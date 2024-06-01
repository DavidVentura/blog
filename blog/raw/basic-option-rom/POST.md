---
title: Learning about PCI-e: Implementing an option ROM
date: 2024-05-27
tags: c, qemu
slug: pcie-option-rom
incomplete: true
description: 
---

In this series, we've been implementing a PCI-e GPU and so far we were able to put some pixels on the (emulated) screen via purpose-built userspace programs.

Now it's time to make the GPU available to the system, and we'll start by making it available to {^UEFI|Unified Extensible Firmware Interface}, which is the system firmware that initializes hardware and loads the operating system.

UEFI does not have built-in drivers for our custom GPU, but it allows for PCI devices to bring their own driver via something called an [Option ROM](https://en.wikipedia.org/wiki/Option_ROM).

An option rom is quite small, just 64 bytes of headers, followed by a few KiB of driver's executable, in {^PE|Portable Executable} format:

<img src="/images/optionrom/headers.svg" style="margin: 0px auto; width: 100%; max-width: 40rem" />

We are going to implement the UEFI driver with [EDK2](https://github.com/tianocore/edk2).

## Hello world
To set up the repo, we follow the [official instructions](https://github.com/tianocore/tianocore.github.io/wiki/Common-instructions):

```bash
git clone 
git submodule update --init --recursive
make -C BaseTools
source edksetup.sh
```


To build the driver, we need to specify in `Conf/target.txt` our platform's target:

```ini
ACTIVE_PLATFORM =OvmfPkg/OvmfPkgX64.dsc
TARGET_ARCH=X64
TOOL_CHAIN_TAG=GCC5
```

and following the [skeleton example](https://github.com/tianocore-docs/edk2-UefiDriverWritersGuide/blob/master/7_driver_entry_point/README.md#example-87-uefi-driver-inf-file) we can create

INF file

```ini
```
driver.c
```c
```

and build it:
```bash
build -m OptionRom/Rom.inf
```

which will generate the `./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi` file

```bash
$ file ./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi
./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi: PE32+ executable (EFI boot service driver) x86-64, for MS Windows, 3 sections
```

We can take the `efi` file and build it into an Option Rom with `EfiRom`:

```bash
./BaseTools/Source/C/bin/EfiRom -f 0x1337 -i 0x1234 -o ./Build/OptionRom.efirom -e ./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi
```

Let's dump the Option Rom metadata to confirm:

```bash
./BaseTools/Source/C/bin/EfiRom -d a.rom 
Image 1 -- Offset 0x0
  ROM header contents
    Signature              0xAA55
    PCIR offset            0x001C
    Signature               PCIR
    Vendor ID               0x1234
    Device ID               0x1337
    Length                  0x001C
    Revision                0x0003
    DeviceListOffset        0x00
    Class Code              0x000000
    Image size              0x2400
    Code revision:          0x0000
    MaxRuntimeImageLength   0x00
    ConfigUtilityCodeHeaderOffset 0x00
    DMTFCLPEntryPointOffset 0x00
    Indicator               0x80   (last image)
    Code type               0x03   (EFI image)
  EFI ROM header contents
    EFI Signature          0x0EF1
    Compression Type       0x0000 (not compressed)
    Machine type           0x8664 (X64)
    Subsystem              0x000B (EFI boot service driver)
    EFI image offset       0x0100 (@0x100)
```


Let's put the driver in a FAT filesystem:

```bash
truncate -s 32M disk.raw
mkfs.fat disk.raw
mcopy -o -i disk.raw Build/OptionRom.efirom ::OptionRom.efirom
```

Now we can load it manually with QEMU:


```bash
$ qemu-system-x86_64 -hda disk.raw -bios /usr/share/ovmf/OVMF.fd
UEFI Interactive Shell v2.2
EDK II
UEFI v2.70 (EDK II, 0x00010000)
Shell> fs0:
FS0:\> loadpcirom OptionRom.efirom
MyOptionRom loaded
Image 'FS0:\OptionRom.efirom' load result: Success
FS0:\> 
```

This confirms that the toolchain is working, and we can now start the real implementation of the driver

## Driver model

UEFI drivers are expected[^1] to follow the driver model which provides a {^[standardized](https://uefi.org/sites/default/files/resources/UEFI_Spec_2_1.pdf)|Section 2.5} way to initialize hardware during the boot process.
These drivers are only really _required_ to implement the Driver Binding protocol, which handles the attachment and detachment of drivers to devices by implementing `Supported()`, `Start()`, and `Stop()`.

The goal of drivers is to produce a protocol on the device handle that abstracts the operations that the device supports. In our case, we want to get a handle to our Pci device with the `PciIoProtocol`, and then install the `GraphicsOutputProtocol`.

{embed-mermaid driver.mmd}

- PciIoProtocol def
- GraphicsOutputProtocol defjkk

set PcdDebugPrintErrorLevel 
- doing something, maybe blit, maybe just show up somewhere??

https://github.com/tianocore-docs/edk2-UefiDriverWritersGuide/tree/master/18_pci_driver_design_guidelines
pci proto -> gop proto


discovery:
- (internal to uefi) PCI bus discovery [wiki link]
- pci rom, look at offset X for magic signature AA 55
- if match, look at subtype UEFI
- register drivers internally via EfiLibInstallDriverBindingComponentName2 

after all drivers are installed,
- per discovered PCI or USB (?) device, run the Supported function in the driver model

Supported decides for a given PCI device (Controller?) whether to take ownership or not (is it true? what if conflict?)

after all drivers are bound, call Start() on them?? maybe

Then Start + Stop

UEFI drivers in bad nutshell

Consume 'lower level' protocols (pci), provide higher level ones (Graphics Output)

other example, consume Graphics Output, provide TextOutput

a shell can be built with TextInput + TextOutput

In Blit, we can implement a naive write to framebuffer memory, by sending 1 DWORD at a time

```c
```

_be patient_
<center><video controls><source  src="/videos/optionrom/no-dma.mp4"></source></video></center>

which is _amazing_ as it shows the option ROM works with an otherwise unmodified UEFI.
at this spoint i spent about 45 min figuring out how to implement a dma transfer, as we did in [the last episode](),

```c
- for (..
- for (..
+ CopyBufferDMA()
```

which is _so much faster_
<center><video controls><source  src="/videos/optionrom/with_dma.mp4"></source></video></center>

However. 

at this point I realized that:
- Gop is a Boot Service
- ExitBootServices is a thing

BootServices vs Run Services


explanation of kernel/efifb using just the framebuffer, video on framebuffer usage from uefi


1. https://tianocore-docs.github.io/edk2-UefiDriverWritersGuide/draft/
1. https://casualhacking.io/blog/2019/12/3/using-optionrom-to-overwrite-smmsmi-handlers-in-qemu
1. https://x86sec.com/posts/2022/09/26/uefi-oprom-bootkit/
1. https://www.intel.co.uk/content/dam/doc/guide/uefi-driver-graphics-controller-guide.pdf
1. https://github.com/artem-nefedov/uefi-gdb
1. https://uefi.org/sites/default/files/resources/UEFI_Spec_2_1.pdf


[^1]: but you can also completely ignore the driver model and just install a protocol during your entrypoint ¯\\\_(ツ)\_/¯

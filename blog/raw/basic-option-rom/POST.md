---
title: Learning about PCI-e: Implementing an option ROM
date: 2024-05-27
tags: c, qemu, uefi
slug: pcie-option-rom
incomplete: true
description: 
---

In this series, we've been implementing a PCI-e GPU and so far we were able to put some pixels on the (emulated) screen via purpose-built userspace programs.

Now it's time to make the GPU available to the system, and we'll start by making it available to {^UEFI|Unified Extensible Firmware Interface}, which is the system firmware that initializes hardware and loads the operating system.

UEFI does not have built-in drivers for our custom GPU, but it allows for PCI devices to bring their own driver packaged in something called an [Option ROM](https://en.wikipedia.org/wiki/Option_ROM).

The format for an option rom is just 64 bytes of headers (split in two), followed by the driver's executable, in {^PE|Portable Executable} format:

<img src="/images/optionrom/headers.svg" style="margin: 0px auto; width: 100%; max-width: 40rem" />


## A 'Hello world' driver

For this post, we are going to implement the UEFI driver with [EDK2](https://github.com/tianocore/edk2), to set up the repo,
we follow the [official instructions](https://github.com/tianocore/tianocore.github.io/wiki/Common-instructions):

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

and build the driver with `build -m OptionRom/Rom.inf` (yes, they named their build command `build`), which will generate the driver, as a PE file at `./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi`

We can now take the driver and build it into an Option Rom with `EfiRom` by passing the Vendor ID (`0x1337`) and the Device ID (`0x1234`):

```bash
./BaseTools/Source/C/bin/EfiRom -f 0x1337 -i 0x1234 -o ./Build/OptionRom.rom -e ./Build/OvmfX64/DEBUG_GCC5/X64/OptionRom.efi
```

Let's dump the Option Rom metadata to confirm:

```bash
./BaseTools/Source/C/bin/EfiRom -d ./Build/OptionRom.rom 
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
mcopy -o -i disk.raw Build/OptionRom.rom ::OptionRom.rom
```

Now we can load it manually with QEMU:


```bash
$ qemu-system-x86_64 -hda disk.raw -bios /usr/share/ovmf/OVMF.fd
UEFI Interactive Shell v2.2
Shell> fs0:
FS0:\> loadpcirom OptionRom.rom
MyOptionRom loaded
Image 'FS0:\OptionRom.rom' load result: Success
```

This confirms that the toolchain is working, and we can now start the real implementation of the driver

## Driver model

UEFI drivers are expected[^1] to follow the driver model which provides a {^[standardized](https://uefi.org/sites/default/files/resources/UEFI_Spec_2_1.pdf)|Section 2.5} way to initialize hardware during the boot process.
These drivers are only really _required_ to implement the Driver Binding protocol, which handles the attachment and detachment of drivers to devices by implementing `Supported()`, `Start()`, and `Stop()`.

First, UEFI will scan the PCI bus for all present devices, registering every Option ROM as a driver.

For each driver, UEFI will call `Supported` with _every_ PCI device

TODO THIS PART
The goal of drivers is to produce a protocol on the device handle that abstracts the operations that the device supports. In our case, we want to get a handle to our Pci device with the `PciIoProtocol`, and then install the `GraphicsOutputProtocol`.

- PciIoProtocol def
- GraphicsOutputProtocol defjkk

Define driver state:
```c
```

_As UEFI code is quite verbose, all code samples are abbreviated, find sources [here]()_

Implementing support:

```c
EFI_STATUS EFIAPI GpuVideoControllerDriverSupported(...) {
  EFI_PCI_IO_PROTOCOL  *PciIo;
  PCI_TYPE00           Pci;
  // Get a handle for the PCI I/O Protocol
  gBS->OpenProtocol(&gEfiPciIoProtocolGuid, (VOID **)&PciIo, ...);
  // Read the PCI Configuration Header from the PCI Device
  PciIo->Pci.Read(PciIo, EfiPciIoWidthUint32, 0, sizeof (Pci) / sizeof (UINT32), &Pci);

  // Release the PCI I/O Protocol
  gBS->CloseProtocol(&gEfiPciIoProtocolGuid, ...);

  // Validate we are talking with the custom GPU
  if (Pci.Hdr.VendorId == 0x1234 && Pci.Hdr.DeviceId == 0x1337) {
    return EFI_SUCCESS;
  }
  return EFI_UNSUPPORTED;
}
```

```c
EFI_STATUS EFIAPI GpuVideoControllerDriverStart (...) {
  // Raise task priority to prevent `Start` from being interrupted
  EFI_TPL OldTpl = gBS->RaiseTPL (TPL_CALLBACK);
  MY_GPU_PRIVATE_DATA *Private = AllocateZeroPool(sizeof(MY_GPU_PRIVATE_DATA));;
  // Get a handle for the PCI I/O Protocol
  gBS->OpenProtocol(&gEfiPciIoProtocolGuid, (VOID **)&Private->PciIo, ...);

  // Read supported attributes
  UINT64 SupportedAttrs;
  Private->PciIo->Attributes(Private->PciIo, EfiPciIoAttributeOperationSupported, 0, &SupportedAttrs);

  // Update attributes
  SupportedAttrs |= EFI_PCI_DEVICE_ENABLE;
  Private->PciIo->Attributes (Private->PciIo, EfiPciIoAttributeOperationEnable, SupportedAttrs, NULL);

  // Install Graphics Output Protocol on this driver
  gBS->InstallMultipleProtocolInterfaces(&Private->Handle, &gEfiGraphicsOutputProtocolGuid, Private->Gop, NULL);

  // Restore the priority of this task
  gBS->RestoreTPL (OldTpl);
}
```

and the entrypoint of the EFI only configures itself as a driver:
```c
EFI_DRIVER_BINDING_PROTOCOL gGpuVideoDriverBinding = {
  GpuVideoControllerDriverSupported,
  GpuVideoControllerDriverStart,
  GpuVideoControllerDriverStop,
  0x10, // version
  NULL,
  NULL
};

EFI_STATUS EFIAPI OptionRomEntry(...) {
  EFI_STATUS Status = EfiLibInstallDriverBindingComponentName2 (
	  ...,
      &gGpuVideoDriverBinding,
      ...,
      );
  ASSERT_EFI_ERROR (Status);
  return Status;
}
```

at this point we have a driver that registers itself as a Graphics Output (GOP) and does nothing else.

Implementing GOP

```diff
+ GopSetup(Private)
  gBS->InstallMultipleProtocolInterfaces(&Private->Handle, &gEfiGraphicsOutputProtocolGuid, Private->Gop, NULL);
```

```c
EFI_STATUS EFIAPI GopSetup(IN OUT MY_GPU_PRIVATE_DATA *Private) {
  EFI_STATUS Status;
  // Initialize the GOP protocol with our 3 callbacks
  Private->Gop.QueryMode = MyGpuQueryMode;
  Private->Gop.SetMode = MyGpuSetMode;
  Private->Gop.Blt = MyGpuBlt;

  // Fill in the available modes, for now, this is static
  Private->Info.Version = 0;
  Private->Info.HorizontalResolution = 640; // hardcoded on the adapter
  Private->Info.VerticalResolution = 480;
  Private->Info.PixelFormat = PixelBlueGreenRedReserved8BitPerColor;
  Private->Info.PixelsPerScanLine = Private->Info.HorizontalResolution;

  Private->Gop.Mode = AllocateZeroPool(sizeof(EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE));
  Private->Gop.Mode->MaxMode = 1;
  Private->Gop.Mode->Mode = 0;
  Private->Gop.Mode->Info = &Private->Info;
  Private->Gop.Mode->SizeOfInfo = sizeof(EFI_GRAPHICS_OUTPUT_MODE_INFORMATION);
  UINT32 FbSize = Private->Info.HorizontalResolution * Private->Info.VerticalResolution * sizeof(EFI_GRAPHICS_OUTPUT_BLT_PIXEL);
  Private->Gop.Mode->FrameBufferBase = AllocateZeroPool(FbSize);
  Private->Gop.Mode->FrameBufferSize = FbSize;
}
```

and then we need to implement the 3 callbacks for the protocol:

QueryMode: stumped me bc it needs to return a freshly-allocated pool

QueryMode needs to return a newly-allocated Info which specifies the current graphics resolution, as we only support 1 resolution, we copy it from the driver state
```c
EFI_STATUS EFIAPI MyGpuQueryMode(..., OUT UINTN *SizeOfInfo, OUT EFI_GRAPHICS_OUTPUT_MODE_INFORMATION **Info) {
  MY_GPU_PRIVATE_DATA *Private = MY_GPU_PRIVATE_DATA_FROM_THIS(This);
  *SizeOfInfo = sizeof(EFI_GRAPHICS_OUTPUT_MODE_INFORMATION);
  // Info must be a newly allocated pool
  *Info = AllocateCopyPool (*SizeOfInfo, &Private->Info);
  return EFI_SUCCESS;
}
```

the emphasis in copy/newly allocated is because i spent hours trying to figure out why i was getting this assertion error

```
ASSERT edk2/MdeModulePkg/Core/Dxe/Mem/Pool.c(721): Head->Signature == ((('p') | ('h' << 8)) | ((('d') | ('0' << 8)) << 16)) || Head->Signature == ((('p') | ('h' << 8)) | ((('d') | ('1' << 8)) << 16))
```

when not using the `AllocatePool` family for the output buffer - the docs state that it's a callee-allocated pool LINK


SetMode asks us to reconfigure the output to one of thesupported formats, but we don't really support other resolutions right now, so it's a no-op:

```c
EFI_STATUS EFIAPI MyGpuSetMode(...) {
    return EFI_SUCCESS;
}
```

and the interesting function, Blt, which takes a lot of parameters and supports multiple modes. You can find the documentation [here](https://uefi.org/specs/UEFI/2.10/12_Protocols_Console_Support.html#efi-graphics-output-protocol-blt) -- let's start with support for full screen blits only:

The most naive implementation: set the value of each pixel, one at a time, via a PCI write
```c
EFI_STATUS EFIAPI MyGpuBlt(
    IN  EFI_GRAPHICS_OUTPUT_PROTOCOL       *This,
    IN  EFI_GRAPHICS_OUTPUT_BLT_PIXEL      *BltBuffer  OPTIONAL,
    IN  EFI_GRAPHICS_OUTPUT_BLT_OPERATION  BltOperation,
    IN  UINTN                              SourceX,
    IN  UINTN                              SourceY,
    IN  UINTN                              DestinationX,
    IN  UINTN                              DestinationY,
    IN  UINTN                              Width,
    IN  UINTN                              Height,
    IN  UINTN                              Delta
	) {
	MY_GPU_PRIVATE_DATA *Private = MY_GPU_PRIVATE_DATA_FROM_THIS(This);
	for(int y=0; y<Private->Info.VerticalResolution;y++){
		for(int x=0; x<Private->Info.HorizontalResolution;x++){
			UINT32 i = (Private->Info.HorizontalResolution * y + x) * 4;
			UINT32 r = ((char*)Private->Gop.Mode->FrameBufferBase)[i+2];
			UINT32 g = ((char*)Private->Gop.Mode->FrameBufferBase)[i+1];
			UINT32 b = ((char*)Private->Gop.Mode->FrameBufferBase)[i+0];
			UINT32 pixval = b | (g << 8) | (r << 16);
			Private->PciIo->Mem.Write (
					Private->PciIo,       
					EfiPciIoWidthUint32,  // Width
					0,                    // BarIndex
					i,                    // Offset
					1,                    // Count
					&pixval       		  // Value
					);
		}
	}
}
```

And now, _be patient_ for the grand reveal:

<center><video controls><source  src="/videos/optionrom/no-dma.mp4"></source></video></center>

which is _amazing_ as it shows the option ROM works with an otherwise unmodified UEFI.

It also _may_ be a _tad_ slow, so at this point I spent about 45 min researching and implementing DMA transfers, as we did in [the last entry](/pcie-driver-dma.html), which ended up looking something like this:

```diff
-    for(int y=0; y<Private->Info.VerticalResolution;y++){
-    	for(int x=0; x<Private->Info.HorizontalResolution;x++){
-       }
-    }
+    CopyBufferDMA()
```

and it was _so much faster_
<center><video controls><source  src="/videos/optionrom/with_dma.mp4"></source></video></center>

**However**

at this point I realized that:
- Gop is a Boot Service
- ExitBootServices is a thing

BootServices vs Run Services

Services = Functions

Runtime Services are the functions that remain available after the operating system has taken control, such as `GetTime`, `SetTime`, `GetVariable`.

Boot Services are the functions which are _only_ available before the operating system takes control.

The operating system "taking control" is defined as the point in time on which `ExitBootServices` is called.

So, whenever Linux starts booting, it'll call `ExitBootServices()`, and our GOP's `Blit` function will no longer be callable :(

Gop->Mode:
```c
typedef struct {
	UINT32 MaxMode;
	UINT32 Mode;
	EFI_GRAPHICS_OUTPUT_MODE_INFORMATION *Info;
	UINTN SizeOfInfo;
	EFI_PHYSICAL_ADDRESS FrameBufferBase;
	UINTN FrameBufferSize;
} EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE```

`FrameBufferBase`

While the GOP can't be accessed, the underlying framebuffer remains valid (unless we actively free/close it), so what Linux will do (in `efifb`) is directly write to the framebuffer.

As direct writes (no DMA) are what linux will do, TODO: pending if FBCON loads with my driver, we should do the same.

- Get BAR#1 address
- Store it
- Call `FrameBufferBlt`

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



explanation of kernel/efifb using just the framebuffer, video on framebuffer usage from uefi


1. https://tianocore-docs.github.io/edk2-UefiDriverWritersGuide/draft/
1. https://casualhacking.io/blog/2019/12/3/using-optionrom-to-overwrite-smmsmi-handlers-in-qemu
1. https://x86sec.com/posts/2022/09/26/uefi-oprom-bootkit/
1. https://www.intel.co.uk/content/dam/doc/guide/uefi-driver-graphics-controller-guide.pdf
1. https://github.com/artem-nefedov/uefi-gdb
1. https://uefi.org/sites/default/files/resources/UEFI_Spec_2_1.pdf


[^1]: but you can also completely ignore the driver model and just install a protocol during your entrypoint ¯\\\_(ツ)\_/¯

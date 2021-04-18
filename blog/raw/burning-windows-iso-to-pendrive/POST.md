---
title: Bootable Windows 10 iso from linux
date: 2017-09-17
tags: 
description: 
---
For some damn reason windows isos are not dd-able.

I found instructions that worked, written by `Lithium79` on arstechnica forums [Link](https://arstechnica.com/civis/viewtopic.php?p=30645773&sid=2a5bbbcdbbcf829fdefc7de83b9dd9e5#p30645773)

```bash
# fdisk /dev/sdY

create single partition type 7+bootable partition

# mkfs.ntfs -f /dev/sdY1
# ms-sys -7 /dev/sdY

# mount -o loop win7.iso /mnt/iso
# mount /dev/sdY1 /mnt/usb
# cp -r /mnt/iso/* /mnt/usb/
# sync
# umount /mnt/usb
# eject /dev/sdY
```

and, as he says, if you don't have ms-sys you can install it from [Source](http://ms-sys.sourceforge.net/). You just have to run `make`.

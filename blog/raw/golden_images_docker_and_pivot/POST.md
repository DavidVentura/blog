---
title: Docker-based images on baremetal
date: 2021-01-23
tags: systems-deployment
description: The process behind creating multiple flash-able OS disk images from Dockerfiles and swapping between them on the host
---
Exploring how to achieve some of the properties of containerized deployments on bare
metal servers.

The properties I'm interested in for this post are:

* Fast deployment (+ fast rollbacks)
* Testing different OS versions with production workloads

I investigated [before](/creating-a-golden-centos-image.html) how to generate and flash custom OS images, and we can keep building
based on those findings.

The changes will be:

* Building the images with Docker instead of bash scripts
* Multiple images in one disk

The change to Docker comes from tooling better being available, integrations with CI
and to avoid reimplementing the layer+caching logic.

# Docker based OS image

To contrast how easy it easy to start building the base image with docker, we can look at my initial Dockerfile:

```
FROM centos:7.9.2009
RUN yum install -y systemd kernel
```

Something that I know before even giving the base image a spin is that there is no init manager (systemd) and
no kernel on container base images, because it is completely unnecessary.

We can build this to get at the files that are inside

```bash
docker build -f centos7.9 -t 7.9 .
```

Sadly, you can't `export` an **image**'s filesystem[^1], you have to export a **container**'s
filesystem -- the difference here being that a container is an instance of an image.

```bash
$ CONTAINER_ID=$(docker run -itd 7.9 /bin/sh)
$ docker export $CONTAINER_ID | sudo tar -C 79
$ docker stop $CONTAINER_ID
```

With the container data we want to put on disk, we have to do the same as in [this post](/creating-a-golden-centos-image.html) so I will just list the
repeated steps and go into more detail for the new ones.

## Create the disk

```bash
dd if=/dev/zero of=$DISK bs=1G count=3
```

Partition it (2 partitions, will use one per image)
```bash
parted -s -a optimal $DISK mklabel msdos
parted -s -a optimal $DISK mkpart primary 0% 50% mkpart primary 50% 100% set 1 boot on
```
For some reason, running the other commands at the same time as `mklabel` had no effect.


Write GRUB to the boot sector
```bash
dd if=/usr/lib/grub/i386-pc/boot.img of=$DISK bs=446 count=1 conv=notrunc
dd if=core.img of=$DISK bs=512 seek=1 conv=notrunc
```

Now, for each partition we have to mount it and write the image data to it.
```bash
$ parted -s $DISK unit B print all | grep -A 2 Number
Number  Start        End          Size         Type     File system  Flags
 1      1048576B     1610612735B  1609564160B  primary  xfs          boot
 2      1610612736B  3221225471B  1610612736B  primary  xfs
```

With the start + size fields we can mount each partition in a loop device
```
$ LOOP=$(sudo losetup -f)
$ sudo losetup $LOOP $DISK --offset $OFFSET --maxsize $SIZE
$ sudo mkfs.xfs -f $LOOP
$ sudo mount $LOOP $DIR
```

Copy the grub modules and grub config
```
$ sudo mkdir -p $DIR/boot/grub/i386-pc
$ sudo cp /usr/lib/grub/i386-pc/* 79/boot/grub/i386-pc
$ sudo cp embedded_combined 79/boot/grub/grub.cfg

$ sudo umount 79
$ sudo losetup -D $LOOP
```

The grub config has to have one entry per partition, pointing to their respective kernel and initrd files:

```
set timeout=1
menuentry "centos 8.3" {
    set root=(hd0,msdos2)
    linux  /boot/a09b09cbf0ce4eea811f98ace1b0f17d/4.18.0-240.10.1.el8_3.x86_64/linux root=/dev/vda2 rw console=tty0 console=ttyS0,115200
    initrd /boot/a09b09cbf0ce4eea811f98ace1b0f17d/4.18.0-240.10.1.el8_3.x86_64/initrd
}
menuentry "centos 7.9" {
    set root=(hd0,msdos1)
    linux  /boot/vmlinuz-3.10.0-1160.11.1.el7.x86_64 root=/dev/vda1 rw console=tty0 console=ttyS0,115200 modprobe.blacklist=floppy
    initrd /boot/initramfs-3.10.0-1160.11.1.el7.x86_64.img
}
```

# Problems booting the image

## Initrd does not support virtio disks

At least on the CentOS7.9 image, the `virtio` drivers are not built into the initrd, so it can't see the disk.

In the dockerfile we can re-generate the initrd with `dracut`, although given that we are running in a container we have
to specify a bunch of options about on which kernel this will actually run (not the currently running kernel, as is the
default).

```Dockerfile
RUN dracut --kmoddir /lib/modules/3.10.0-1160.11.1.el7.x86_64/ --kver 3.10.0-1160.11.1.el7.x86_64 --add-drivers "virtio_blk virtio_scsi xfs" --no-hostonly -M -f /boot/initramfs-3.10.0-1160.11.1.el7.x86_64.img
```

## Initrd does not support XFS

Similar to previous step, xfs is unsupported so we have to tweak the dracut call with an extra driver (`xfs`) and `--filesystems
xfs`

## Older CentOS can't mount newer XFS versions (as built on the host machine)

When booting, the step that tried to boot the new fs from the initramfs would fail with a weird message:
```
XFS superblock has read-only compatible features (0x4) enabled
```

This can be mitigated by disabling reflink when building the fs: `mkfs.xfs -m reflink=0`, found 
[here](https://github.com/ceph/ceph-csi/issues/966#issuecomment-661703389).

## Default systemd target does not exist

Default target is `graphical-target`, which is not installed/configured so boot stalls

```bash
$ ls -lhrt ./usr/lib/systemd/system/default.target
lrwxrwxrwx 1 root root 16 Dec 18 00:30 ./usr/lib/systemd/system/default.target -> graphical.target
```

Fix by adding a step to the Dockerfile:
```
RUN cd usr/lib/systemd/system && ln -sf multi-user.target default.target
```

## Boot seems to progress normally but it never displays a TTY

The `Welcome to CentOS` message along with a bunch of `[OK] Service XYZ` messages fly through and suddenly... stall,
without ever showing a login prompt.

Enable extra debug on systemd:

[On the kernel cmdline](https://freedesktop.org/wiki/Software/systemd/Debugging/), add 
`systemd.log_level=debug systemd.log_target=console console=ttyS0,38400 console=tty1`

which will spam the console endlessly... and uselessly as you can't read through so much text.

Luckily, we can run this disk as it is in a VM, and redirect the VM's serial device to a file:

```bash
$ kvm -drive file=$DISK,format=raw,if=virtio -m 2048 -chardev stdio,id=char0,logfile=serial.log,signal=off -serial chardev:char0
```

In this file, grepping for `tty` yields a very interesting message:
```
getty.target: Cannot add dependency job, ignoring: Unit getty.target is masked.
```

The tty job is disabled! Of course we won't see a log-in prompt!! Hours of debug are solved with a simple line:
```
RUN systemctl unmask getty.target
```

# Toggling between OS versions

At this point we have everything we need to write multiple OS images to the same disk and boot to each.

The simplest option here would be to upgrade the GRUB defaults and just reboot, but that takes "long" -- depending on
hardware configuration a reboot can take up to 20 minutes, 19 of which are spent on POST. Luckily there's a way to "warm
reboot" by loading a new kernel and jumping into it, this process is called `kernel execute` (`kexec` for short) and it
has similar characteristics to `exec` that is, switch a running image (process, kernel) with a new one and execute it.

With everything in place, `kexec` is super straight forward to run:

```bash
grep $other_disk /boot/grub/grub.cfg | awk '{$1=$2=""; print $0}'
kexec -l /$other_disk/boot/vmlinuz* --initrd=/$other_disk/boot/init* --append="$args"
kexec -e
```

That's it! you are now rebooting into another kernel.

Small demo:
<asciinema-player poster="/images/kexec-demo.svg" src="/casts/kexec-demo.cast" cols="118" rows="31" preload=""></asciinema-player>

[^1]: flattened; you can get every layer individually with `docker save`</span>

---
title: Creating a golden CentOS image
date: 2019-12-24
tags: systems-deployment
description: How to create a flash-able CentOS disk image
---
What is involved in creating a disk image that can be `dd`'d to a disk and boot
into a working system? Is it too much? Why is everyone still using
kickstart/preseed for images?

From a high-level overview, there are three things that need to be solved:

* Creating a useful filesystem, containing all the needed software
* Converting this filesystem to a disk image
* Making the disk image bootable


# Creating a filesystem

This post focuses on CentOS but it should be quite similar for debian-based
distros.

What's needed to bootstrap a system? Only what's needed to bootstrap the package
manager! We can work our way up from there.

## System packages
CentOS provides a `centos-release` package, which is (conveniently) enough to bootstrap `yum`:

```
$ rpm -qlp centos-release-7-7.1908.0.el7.centos.x86_64.rpm
/etc/centos-release
/etc/centos-release-upstream
/etc/issue
/etc/issue.net
/etc/os-release
/etc/pki/rpm-gpg
/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-Debug-7
/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-Testing-7
/etc/redhat-release
/etc/rpm/macros.dist
/etc/system-release
/etc/system-release-cpe
/etc/yum.repos.d/CentOS-Base.repo
/etc/yum.repos.d/CentOS-CR.repo
/etc/yum.repos.d/CentOS-Debuginfo.repo
/etc/yum.repos.d/CentOS-Media.repo
/etc/yum.repos.d/CentOS-Sources.repo
/etc/yum.repos.d/CentOS-Vault.repo
/etc/yum.repos.d/CentOS-fasttrack.repo
/etc/yum/vars/contentdir
/etc/yum/vars/infra
/usr/lib/systemd/system-preset/85-display-manager.preset
/usr/lib/systemd/system-preset/90-default.preset
/usr/share/centos-release/EULA
/usr/share/doc/centos-release/Contributors
/usr/share/doc/centos-release/GPL
/usr/share/doc/redhat-release
/usr/share/redhat-release
```

We don't want to install this in the main system though, so we'll create a
directory to use as a chroot.

```
CHROOT=/tmp/chroot
mkdir -p $CHROOT
yum --installroot=$CHROOT install centos-release-7-7
```

From now on, we can install all system packages that we want with yum, the
minimal amount that we need for a reasonable system is:
`yum --installroot=$CHROOT install yum openssh-server systemd`

## Users

Where does linux store users and password? `/etc/passwd` and `/etc/shadow`,
but we don't have those yet so we can't log in.

For a basic demonstration, you could do this:

```
echo 'root:x:0:0:root:/root:/bin/bash' > $CHROOT/etc/passwd
echo 'root:$6$L08Ghg3slCgBXyYP$jsyibvI2vKpBgm8ikZGRMeqknY6VqNuiy1xXk3uupc8KNwVOcx7yXscmTSVVfnnaB5sFFsKub1SiEyo7ITs3M0:17834:0:99999:7:::' > $CHROOT/etc/shadow
```

That root password is 'password'. Pay a lot of attention at how I'm using
single quotes for `/etc/shadow`, the type of encryption is determined by `$6$`
and the character `$` is valid for the password hash, so if you use
double-quotes, those will be expanded and you'll spend a lot of time trying to
figure out what's going on.

## Kernel and initramfs

The early boot stage is set-up by the initramfs, which is not currently
available in our chroot, and we are also missing a kernel.

Luckily we can just copy these from the bootstrapping machine:

```
cp /boot/initramfs-$(uname -r).img $CHROOT/boot/initramfs.igz
cp /boot/vmlinuz-$(uname -r)       $CHROOT/boot/vmlinuz
```

Note how we are leaving the versions out -- these machines will never see an
upgrade. We'll just create new images and re-flash them.


# Converting the filesystem to an image

Ok, we have files on disk but we need to have a "disk". For a "disk" we need
both a partition table and *at least* a single partition.

How big should our disk be? Let's check how big our chroot is:

```
$ du -sh $CHROOT
582M /tmp/chroot
```

Let's create an 800MB disk (could be smaller, but because we'll be flashing this
as-is I don't want the inodes to be squashed *too* close together. I don't know
how much this will affect the system after the fs is expanded):
`dd if=/dev/zero of=disk.img bs=1m count=800`

On this disk, we want to create both the partition table and the only partition
we'll have.

```
$ fdisk disk.img

Command (m for help): o
Created a new DOS disklabel with disk identifier 0x42d8352b.

Command (m for help): n
Partition type
   p   primary (0 primary, 0 extended, 4 free)
   e   extended (container for logical partitions)
Select (default p): p
Partition number (1-4, default 1): 1
First sector (2048-1638399, default 2048):
Last sector, +/-sectors or +/-size{K,M,G,T,P} (2048-1638399, default 1638399):

Created a new partition 1 of type 'Linux' and of size 799 MiB.

Command (m for help): a
Selected partition 1
The bootable flag on partition 1 is enabled now.

Command (m for help): w
The partition table has been altered.
Syncing disks.
```

We have a disk now, but as it's not a real disk, it will not be populated under
`/dev/sdx` (and `/dev/sdx1` for the partition), so how do we mount it? We can
create a loopback device with the `losetup` tool:

`losetup /dev/loop0 disk.img --offset $((2048*512))`, 2048 is the number of the
first sector of the partition, and 512 comes from the disk sector size.

The partition now exist, but it has no filesystem on it, that's an easy thing to
solve: `mkfs.xfs /dev/loop0`

We can now `mount /dev/loop0 disk_image/` and then `rsync -ar $CHROOT/* disk_image/`.

Let's unmount the disk and try to boot it with `kvm -hda disk.img`:

```
Booting from Hard Disk...
(hangs)
```

# Making the disk image bootable

Why does the image hang? Well, the boot process from BIOS involves looking up
what to boot by checking the MBR, which lives in the first 446 bytes of the disk
(the first sector), and we have not written anything there yet. See [this](https://en.wikipedia.org/wiki/Master_boot_record#Sector_layout).

Conveniently, we can get this MBR from GRUB:
`dd if=/usr/lib/grub/i386-pc/boot.img of=disk.img bs=446 count=1 conv=notrunc`

Now we have some code in the MBR specifying that the next code to be execute is
present at the address 512 in the disk.

What can we put there? GRUB.

For that, we have to generate a GRUB image with the modules that we want to have
available (and we really want to be able to boot xfs), and then flash that
starting on the byte number 512 on the disk:

```
grub2-mkimage -O i386-pc -o ./core.img -p '(hd0,msdos1)/boot/grub' biosdisk part_msdos xfs
dd if=core.img of=disk.img bs=512 seek=1 conv=notrunc
```

We only build this 3 modules as the space for `core.img` is reasonably limited
(1023.5KB, which is 1024\*512-512 bytes for the MBR), but grub still needs to
load a few more modules, like the ones used for text rendering and keyboard
input, so we have to put those in the filesystem.

Without adding the modules we just get this:

```
Booting from Hard Disk...
error: file `/boot/grub/i386-pc/normal.mod' not found.
Entering rescue mode...
grub rescue>
```

Re-mount the `disk.img` and add the modules to it:

```
mount /dev/loop0 $TARGET
mkdir -p $TARGET/boot/grub/i386-pc/
cp /usr/lib/grub/i386-pc/* $TARGET/boot/grub/i386-pc/
```

It boots to grub!

```

                             GNU GRUB  version 2.02

   Minimal BASH-like line editing is supported. For the first word, TAB
   lists possible command completions. Anywhere else TAB lists possible
   device or file completions.


grub>
```


Ah, yes. We didn't tell grub what to do..  let's add 

```
set timeout=5
menuentry "regular_startup" {
    linux   /boot/vmlinuz quiet root=/dev/sda1
    initrd  /boot/initramfs.igz
}
```

to `/boot/grub/grub.cfg` (grub.cfg is the default name that grub looks for, but
/boot/grub is what we passed to `grub2-mkimage` before)

![](/images/vm_bootstrapping/1_grub_entry.png)

The grub entry is alive! But..

# Finishing touches

When booting, I saw a few units pass by in red before the login prompt popped
up, by doing some quick investigation
![](/images/vm_bootstrapping/2_boot_ro.png)

I can see that `/dev/sda1` is mounted *readonly*. We *can* remount it as rw so
it's not some missing driver, we are just missing `/etc/fstab`.

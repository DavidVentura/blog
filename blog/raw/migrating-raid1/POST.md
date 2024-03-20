---
title: Migrating single disk to RAID1 on Debian
date: 2016-10-19
tags: homelab
description: 
---
I have set up a system with /dev/sda as its only disk.
I want to avoid any downtime and unplanned surprises (disks deciding to die) so I thought I'd set up the system in a RAID1.

So I need to:

1. Copy the partition table from sda to sdb
2. Create the disk array with the new disk and a *missing* disk
3. Create filesystems on the new partitions (sdb)
4. Set up mdadm
5. Copy the data from sda to sdb.
6. Check the data on sdb.
7. Modify fstab to boot from the new array.
 1. Update GRUB to boot from the array.
8. Reboot to the *new* rootfs (the array)
9. Add the old device to the new array.
 1. Update mdadm's config to consider the new device.


#####Copying the partition table

Use sfdisk to dump the partition table and repartition the new disk

```bash
# sfdisk -d /dev/sda
# partition table of /dev/sda
unit: sectors

/dev/sda1 : start=     6144, size= 29294592, Id=ef, bootable
/dev/sda2 : start= 29300736, size=947472432, Id=83
```

So:
`# sfdisk -d /dev/sda | sfdisk --force /dev/sdb`

Clones the partition layout.

#####Create the disk array

```
# mdadm --create /dev/md0 --level=1 --raid-disks=2 /dev/sda1 missing
# mdadm --create /dev/md1 --level=1 --raid-disks=2 /dev/sda2 missing
```
#####Create filesystems on the new partitions

```
mkfs.ext4 /dev/md0
mkfs.ext4 /dev/md1
```
#####Set up mdadm
`mdadm --examine --scan >> /etc/mdadm/mdadm.conf`


#####Copy the data from sda to sdb.

```
# mkdir /mnt/{md0,md1}
# mount /{dev,mnt}/md0
# mount /{dev,mnt}/md1
# rsync -aAxXv --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found"} / /mnt/md0

# rsync -aAXv /home/ /mnt/md1
```

rsync for / was taken from the arch wiki (I added -x).

#####Check the data on sdb.

Checking the data is complex. Do the same thing you do to check your backups.

The most trivial thing you can do (if there is no writing to the fs or you can check the differences by hand) is, at the very least, check tree sizes with `du`.

#####Modify fstab to boot from the new array

Take the UUIDs from 
`# blkid /dev/md0 /dev/md1`
and use them to replace the UUIDs on `/etc/fstab`. I suggest you leave the old lines commented. Just in case.

(remember to sync this file to the other disk)

Then just `grub-install /dev/sdb`

#####Add the old device to the new array.

Check the array status with `cat /proc/mdstat`

```
# mdadm --add /dev/md0 /dev/sda1
# mdadm --add /dev/md1 /dev/sda1
```
Update mdadm's config, like before:

`mdadm --examine --scan >> /etc/mdadm/mdadm.conf`

And, to be safe, put GRUB everywhere.

```
grub-install /dev/sda
grub-install /dev/sdb
update-grub
```

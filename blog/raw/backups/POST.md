---
title: Backups, Backups, Backups
date: 2017-02-23
tags: backups, bash
description: 
---
I reached a point where I could recreate all (or most) of my labs with ansible. What I had not yet configured is an extensive backup system. I'll explain here what I did.


## Backing everything up to a central location
For this I use a combination of rsnapshot on the server where everything ends up and bash scripts.

Some of the entries as an example:

```
backup_script   /storage/scripts/backup/db.sh       db/
backup_script   /storage/scripts/backup/pfsense.sh  pfsense/
backup_script   /storage/scripts/backup/gogs.sh     gogs/

# LOCALHOST
backup  /home/david/git         localhost/home/david/
backup  /etc/                   localhost/
backup  /var/lib/lxc/           localhost/
backup  /storage/scripts/       localhost/

#NYC1
backup  root@nyc1:/etc/                     eba/
backup  root@nyc1:/backup/mysql/latest/*    eba/mysql/      +rsync_long_args=--no-relative
backup  root@nyc1:/backup/mongo/latest/*    eba/mongo/      +rsync_long_args=--no-relative

```

The `db.sh` script:
```bash
ssh root@db "mysqldump --all-databases --events --routines --triggers --single-transaction | gzip --rsyncable -3" > backup.sql.gz
```

The `gogs.sh` script:

```bash
ssh root@gogs "cd /home/git/gogs; tar c data | gzip --rsyncable" > gogsdata.tar.gz
ssh root@gogs "cd /home/git; tar c gogs-repositories | gzip --rsyncable" > gogs-repositories.tar.gz
```

This ends up filling and rotating 7 `daily` backups, which become 3 `weekly` backups and 3 `monthly` backups, and with the magic of storing only diffs this only takes about ~2x the space of the original backup.

## Cloning the central backup to an external device

While the above backups are on a RAID1, nothing saves me from deleting everything or the Disks/server exploding.

So I need to have an offline backup. I did this by automating completely the process:

### Automounting the device:

You need to get the UUID of your device with something like `blkid`.

`/etc/udev/rules.d/70-usb-hdd.rules`
```
ACTION=="add", KERNEL=="sd?1", ENV{ID_FS_UUID}=="14421387-1d03-4712-9f70-80a917f64b32", RUN+="/bin/mount /mnt/usbbackup", SYMLINK+="externalhdd"
```

### Triggering backup on mount

I wrote a systemd service ( `/etc/systemd/system/rsync-to-external.service`) that starts backing up to the external device upon 'creation' of `/dev/externalhdd`


```
[Unit]
After=dev-externalhdd.device

[Service]
ExecStart=/storage/scripts/rsync-to-external.sh

[Install]
WantedBy=dev-externalhdd.device
```

### Backing files up

I wrote this script to rsync the backups to an external disk and email me everything that's going on. I'm considering using rsnapshot to keep the external backup versioned.

```bash
#!/bin/bash

set -e

LOCKFILE=/tmp/usbbackup.lock
ERRFILE=/tmp/usbbackup.err
EMAIL="red@acted.com"

function cleanup {
        echo "Removing /tmp/backuplock"
        if [ -f $LOCKFILE ]; then
                rm $LOCKFILE
        fi
}

trap cleanup EXIT

function mailerr {
        echo $1 | mailx -s '[ERROR] rsync usb backup' $EMAIL
}

if [ $(id -u) -ne 0 ]; then
        echo 'Run as root'
        exit 1
fi

if [ -f $ERRFILE ]; then
        mailerr "Previous Error backing up!"
        exit 1
fi

mounted=$(mount | grep -l usbbackup | wc -l )
if [ $mounted -eq 0 ]; then
        mailerr "Device not mounted!!"
        exit 1
fi

touch $LOCKFILE
echo "Starting backup to external device" | mailx -s '[INFO] rsync usb backup' $EMAIL
rsync -av /backup/rsnapshot/daily.0/ /mnt/usbbackup/ >/tmp/usbbackup 2>&1 

if [ $? -ne 0 ]; then
        mailerr "RSYNC Error backing up!"
        exit 1
fi

umount /mnt/usbbackup/
echo "unmounting"
echo "Finished backup to external device" | mailx -s '[OK] rsync usb backup' $EMAIL
```

### Actually backing files up

This would never really happening if there wasn't something pestering me about it. So I wrote a script and stuck it in a cronjob

```
0    */12   *   *   *   /storage/scripts/check-last-backup.sh
```

```bash
#!/bin/bash
set -e

if [ ! -f /tmp/usbbackup ]; then
        echo "touch /tmp/usbbackup or run a backup" | mailx -s '[Warning] No Last backup file!!' $MAIL #In case of server reboot
        exit 1
fi

now=$(date +%s)
last=$(stat -c %Y /tmp/usbbackup)
days=$(echo "($now-$last)/86400" | bc)

if [ $days -ge 6 ]; then
        echo "Go plug in the disk now" | mailx -s '[Warning] Last backup is over a week old' $MAIL
fi
```

## Removing the disk so it's *offline* backup
Same thing as the previous point, the first time I ran the backups I left the drive plugged in for 2 days. This means it's not an offline backup anymore, so I wrote another script to check and pester me every **10 minutes** to go and disconnect it.

```
*/10 *      *   *   *   /storage/scripts/check-external-backup.sh
```

```bash
#!/bin/bash
set -e
backing_up=0
mounted=0
connected=0

if [ $(mount | grep -c usbbackup) -gt 0 ]; then
        mounted=1
fi


usb=$(lsusb | grep -c "1058:0740")
if [ -L /dev/externalhdd ] || [ $usb -ne 0 ]; then
        connected=1
fi

if [ -f /tmp/usbbackup.lock ]; then
        backing_up=1
fi

if [ $backing_up -eq 1 ]; then
        exit 0
fi

if [ $mounted -eq 1 ]; then
        echo "The backup disk is mounted and the backup is done" | mailx -s '[Warning] USB Disk is still mounted' $MAIL
        exit 1
fi

if [ $connected -eq 1 ]; then
        echo "The backup disk is connected (unmounted) and the backup is done" | mailx -s '[Warning] USB Disk is still connected' $MAIL
        exit 1
fi

```

## Cloning the central backup to an offsite server

Having a standard and an offline backup is not enough. I need an offsite backup in case something *really* bad happens.

And given the fact that rsnapshot doesn't accept a target over the network I wrote a script that does something like it (without versioning. I'm thinking about it)

```bash
#!/bin/bash
set -euo pipefail
ROOTPATH="/backup/rsnapshot/daily.0"
function backup() {
        backup_path="$1"
        relative=$(echo $1 | sed "s:^$ROOTPATH/::")
        exclude=""
        while [ $# -gt 1 ]; do
                exclude="$exclude --exclude=$2"
                shift
        done
        /usr/bin/rsync --bwlimit=3m -avz $exclude --delete --numeric-ids --no-relative --delete-excluded "$backup_path" offsite1:backup/"$relative"/
}

backup  $ROOTPATH/server1/mysql/
backup  $ROOTPATH/localhost/            home/   network/ usr/ web/ etc/alternatives etc/ssl
backup  $ROOTPATH/nyc1/                 home/   var/vmail etc/alternatives etc/ssl
backup  $ROOTPATH/db
backup  $ROOTPATH/gogs
backup  $ROOTPATH/mumble
backup  $ROOTPATH/server2                etc/alternatives etc/ssl
backup  $ROOTPATH/pfsense

```


This does not do a 1:1 mirror because:

* I have a measly 4mbit upload and the initial backup would've taken ages
* I'm using `rsync.net` on which I bought a year with 25GB, and the entire backup doesn't fit.

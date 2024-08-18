partition table

GPT

availability

Device-Mapper

david@framework:~/git/blog$ truncate -s 100M device1
david@framework:~/git/blog$ truncate -s 100M device2
david@framework:~/git/blog$ sudo mdadm --create  --level=1 --raid-devices=2 --spare-devices=0 --name='arrayname' device1 device2
mdadm: device device1 exists but is not an md array.
david@framework:~/git/blog$ 

david@framework:~/git/blog$ sudo losetup -f device1
david@framework:~/git/blog$ sudo losetup -f device2
$ sudo losetup -l | grep device
/dev/loop23         0      0         0  0 /home/david/git/blog/device2                       0     512
/dev/loop2          0      0         0  0 /home/david/git/blog/device1                       0     512

david@framework:~/git/blog$ sudo mdadm --create  --level=1 --raid-devices=2 --spare-devices=0 --name='arrayname' /dev/md0 /dev/loop2 /dev/loop23
mdadm: Note: this array has metadata at the start and
    may not be suitable as a boot device.  If you plan to
    store '/boot' on this device please ensure that
    your boot-loader understands md/v1.x metadata, or use
    --metadata=0.90
Continue creating array? yes
mdadm: Defaulting to version 1.2 metadata
mdadm: array /dev/md0 started.
david@framework:~/git/blog$ ls -lhrt /dev/md0
brw-rw---- 1 root disk 9, 0 Aug 11 19:23 /dev/md0
david@framework:~/git/blog$ mdadm -v --detail --scan /dev/md0
mdadm: must be super-user to perform this action
david@framework:~/git/blog$ sudo mdadm -v --detail --scan /dev/md0
ARRAY /dev/md0 level=raid1 num-devices=2 metadata=1.2 name=framework:arrayname UUID=6865ede1:f1a76b48:45071d66:a55755bd
   devices=/dev/loop2,/dev/loop23

david@framework:~/git/blog$ hexdump -C device1
00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
*
00001000  fc 4e 2b a9 01 00 00 00  00 00 00 00 00 00 00 00  |.N+.............|
00001010  68 65 ed e1 f1 a7 6b 48  45 07 1d 66 a5 57 55 bd  |he....kHE..f.WU.|
00001020  66 72 61 6d 65 77 6f 72  6b 3a 61 72 72 61 79 6e  |framework:arrayn|
00001030  61 6d 65 00 00 00 00 00  00 00 00 00 00 00 00 00  |ame.............|
00001040  8e f3 b8 66 00 00 00 00  01 00 00 00 00 00 00 00  |...f............|
00001050  00 18 03 00 00 00 00 00  00 00 00 00 02 00 00 00  |................|
00001060  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
*
00001080  00 08 00 00 00 00 00 00  00 18 03 00 00 00 00 00  |................|
00001090  08 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
000010a0  00 00 00 00 00 00 00 00  a5 cc 7f 3a a6 bc 32 e7  |...........:..2.|
000010b0  97 b7 72 89 75 54 b6 2f  00 00 08 00 10 00 00 00  |..r.uT./........|
000010c0  8e f3 b8 66 00 00 00 00  11 00 00 00 00 00 00 00  |...f............|
000010d0  ff ff ff ff ff ff ff ff  6f 63 64 60 80 00 00 00  |........ocd`....|
000010e0  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
*
00001100  00 00 01 00 ff ff ff ff  ff ff ff ff ff ff ff ff  |................|
00001110  ff ff ff ff ff ff ff ff  ff ff ff ff ff ff ff ff  |................|
*
00001200  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
*
06400000
david@framework:~/git/blog$ 

david@framework:~/git/blog$ file device1
device1: Linux Software RAID version 1.2 (1) UUID=6865ede1:f1a76b48:45071d66:a55755bd name=framework:arrayname level=1 disks=2
david@framework:~/git/blog$ file device2
device2: Linux Software RAID version 1.2 (1) UUID=6865ede1:f1a76b48:45071d66:a55755bd name=framework:arrayname level=1 disks=2



filesystem

xfs/ext4/..

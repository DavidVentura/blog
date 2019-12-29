
Recently I did a few installations of a preseeded iso (for centos, "kickstarted"),
but this takes longer than necessary and is just plain wrong; there's no need to
re-do the same work hundreds of times at install time when all servers will end up
being **the exact same**!

This was kicked off on an afternoon when I was flashing my Raspberry Pi, if
these embedded boards can flash an image that's good enough and boot into it,
even when there are some slight discrepancies in the hardware (network is using ethernet or wifi,
sd cards are of different sizes, memory available changes across models, etc),
why can't my servers do it? **Why is no one doing this?** Apart from the fact that
everyone is using docker/kubernetes or something similar, which behaves
similarly to what I want.

## Contents
- [Figuring out what I need](#figuring-out-what-i-need)
- [Generating an initial filesystem](#generating-an-initial-filesystem)
  * [Generating a slightly more useful initial filesystem](#generating-a-slightly-more-useful-initial-filesystem)
  * [Generating the real initramfs](#generating-the-real-initramfs)
- [Flashing a hard drive from initramfs](#flashing-a-hard-drive-from-initramfs)
- [Booting into the new system without re-booting](#booting-into-the-new-system-without-re-booting)
- [Results](#results)

# Figuring out what I need

What I want is simple: generate a "golden" disk image and "flash" it (write it to
disk) without needing physical access

I started my investigation thinking of some magical API that'd be present on
HP's iLO and Dell's iDRAC that would let me write bytes to disk (somehow?) but
apparently this is not the case.

Next I thought about network booting *something*, but I couldn't find anything
online that had this capability, so.. how hard is it to PXE boot a bit of code
that downloads an image from the network and writes it to disk?

For PXE booting you need only two things: the kernel and the initial filesystem
(initramfs).

I will not worry about the kernel at this point as I'll just copy whatever I
have now in `/boot/vmlinuz-$(uname -r)`.

# Generating an initial filesystem

Generating the initial filesystem (initramfs) is not hard, if you are aware that:
* it must be in `cpio` format (apparently some format and utility for tape
backups standardized in '88)
* the kernel will execute whatever it finds in `/init`

First, we need to write an executable that can be kicked off by the kernel.
Remember that unless we provide them, things like dns, libc, etc are not
available. Compiling binaries in a static form is the best route to take.

For this example I picked a basic go example:

initramfs/init.go:
```
package main
import "fmt"
import "time"

func main() {
    fmt.Println("Hi. I will sleep forever now")
    time.Sleep(2 * time.Hour)
}
```

To build the initramfs, we have to list all the files from the point of view of
`/` so that means we have to `cd` into the directory containing all of our
files, and perform the magic incantation that cpio requires: 
`( cd initramfs/; go build init.go; find . | cpio -H newc -o > ../initramfs.raw )`

The initramfs looks like this:

```
initramfs
├── init
└── init.go
```

Although the `.go` file is not required, I'll leave it there as that is my
current repo.

With this initramfs cpio file, we can start a virtual machine by running
`kvm -kernel /boot/vmlinuz-$(uname -r) -initrd initramfs.raw`

![](/images/linux_flashing/1_initrd_hello_world.png)

It works!

You can find the example
[here](https://gitlab.com/davidventura/flash-hdd-over-network/tree/master/1-poc-bootable-initramfs).

## Generating a slightly more useful initial filesystem

Now that we know how the mechanism works we can get a slightly more useful
filesystem and for this we need busybox, as the most-appropiate way of
interacting with a bare-bones file system is with unix tools instead of custom
applications.

Busybox is a set of stripped-down utilities that were designed for exactly this
kind of use-case: a stand-alone minimal interactive system.

First, you need to clone busybox from [here](git@github.com:mirror/busybox.git)
and statically build it with the following script

```bash
make defconfig
make clean && make LDFLAGS=-static -j$(nproc)
```

If this is successful, it will generate a statically compiled busybox binary,
that contains a lot of useful commands

```
$ file busybox/busybox
busybox/busybox: ELF 64-bit LSB executable, x86-64, version 1 (GNU/Linux), statically linked, BuildID[sha1]=2a2d8183ddf2a07a507554c1e5e3f4aec30e040b, for GNU/Linux 3.2.0, stripped
$ ldd busybox/busybox
        not a dynamic executable
$ ./busybox/busybox
Currently defined functions:
        [, [[, acpid, add-shell, addgroup, adduser, adjtimex, arch, arp, arping, ash, awk, base64, basename, bc, beep, blkdiscard, blkid, blockdev, bootchartd, brctl, bunzip2, bzcat, bzip2, cal, cat, chat, chattr, chgrp, chmod, chown, chpasswd, chpst,
        chroot, chrt, chvt, cksum, clear, cmp, comm, conspy, cp, cpio, crond, crontab, cryptpw, cttyhack, cut, date, dc, dd, deallocvt, delgroup, deluser, depmod, devmem, df, dhcprelay, diff, dirname, dmesg, dnsd, dnsdomainname, dos2unix, dpkg, dpkg-deb,
        du, dumpkmap, dumpleases, echo, ed, egrep, eject, env, envdir, envuidgid, ether-wake, expand, expr, factor, fakeidentd, fallocate, false, fatattr, fbset, fbsplash, fdflush, fdformat, fdisk, fgconsole, fgrep, find, findfs, flock, fold, free,
        freeramdisk, fsck, fsck.minix, fsfreeze, fstrim, fsync, ftpd, ftpget, ftpput, fuser, getopt, getty, grep, groups, gunzip, gzip, halt, hd, hdparm, head, hexdump, hexedit, hostid, hostname, httpd, hush, hwclock, i2cdetect, i2cdump, i2cget, i2cset,
        i2ctransfer, id, ifconfig, ifdown, ifenslave, ifplugd, ifup, inetd, init, insmod, install, ionice, iostat, ip, ipaddr, ipcalc, ipcrm, ipcs, iplink, ipneigh, iproute, iprule, iptunnel, kbd_mode, kill, killall, killall5, klogd, last, less, link,
        linux32, linux64, linuxrc, ln, loadfont, loadkmap, logger, login, logname, logread, losetup, lpd, lpq, lpr, ls, lsattr, lsmod, lsof, lspci, lsscsi, lsusb, lzcat, lzma, lzop, makedevs, makemime, man, md5sum, mdev, mesg, microcom, mkdir, mkdosfs,
        mke2fs, mkfifo, mkfs.ext2, mkfs.minix, mkfs.vfat, mknod, mkpasswd, mkswap, mktemp, modinfo, modprobe, more, mount, mountpoint, mpstat, mt, mv, nameif, nanddump, nandwrite, nbd-client, nc, netstat, nice, nl, nmeter, nohup, nologin, nproc, nsenter,
        nslookup, ntpd, nuke, od, openvt, partprobe, passwd, paste, patch, pgrep, pidof, ping, ping6, pipe_progress, pivot_root, pkill, pmap, popmaildir, poweroff, powertop, printenv, printf, ps, pscan, pstree, pwd, pwdx, raidautorun, rdate, rdev,
        readahead, readlink, readprofile, realpath, reboot, reformime, remove-shell, renice, reset, resize, resume, rev, rm, rmdir, rmmod, route, rpm, rpm2cpio, rtcwake, run-init, run-parts, runlevel, runsv, runsvdir, rx, script, scriptreplay, sed,
        sendmail, seq, setarch, setconsole, setfattr, setfont, setkeycodes, setlogcons, setpriv, setserial, setsid, setuidgid, sh, sha1sum, sha256sum, sha3sum, sha512sum, showkey, shred, shuf, slattach, sleep, smemcap, softlimit, sort, split, ssl_client,
        start-stop-daemon, stat, strings, stty, su, sulogin, sum, sv, svc, svlogd, svok, swapoff, swapon, switch_root, sync, sysctl, syslogd, tac, tail, tar, taskset, tc, tcpsvd, tee, telnet, telnetd, test, tftp, tftpd, time, timeout, top, touch, tr,
        traceroute, traceroute6, true, truncate, ts, tty, ttysize, tunctl, ubiattach, ubidetach, ubimkvol, ubirename, ubirmvol, ubirsvol, ubiupdatevol, udhcpc, udhcpc6, udhcpd, udpsvd, uevent, umount, uname, unexpand, uniq, unix2dos, unlink, unlzma,
        unshare, unxz, unzip, uptime, users, usleep, uudecode, uuencode, vconfig, vi, vlock, volname, w, wall, watch, watchdog, wc, wget, which, who, whoami, whois, xargs, xxd, xz, xzcat, yes, zcat, zcip
```


The way to execute any of these commands is to give it as an argument to
busybox, so to execute `ls` you have to execute `./busybox ls`. This is useful,
yet annoying as we don't want to either type all of that, or include it in our
scripts. Helpfully, busybox also includes an installation parameter, which will
make it symlink all of the commands that it contains to `/bin`.

With plenty of shell commands at our disposition, we can replace our golang init
with a shell script:

```
#!/busybox sh
echo hello from sh!
/busybox mkdir /bin
/busybox --install -s /bin
pwd
ls
date
which vi
exec sh
```

and we have all of this with only 2 files in our initramfs

```
$ tree initramfs
initramfs
├── busybox
└── init
```


![](/images/linux_flashing/2_initrd_busybox.png)

It works as well!.


You can find the example [here](https://gitlab.com/davidventura/flash-hdd-over-network/tree/master/2-bootable-busybox).

## Generating the real initramfs

For the actual initramfs we want a few things:

* Network connectivity
* A program that can download files over network
* To be able to mount the freshly-flashed filesystem

Keep in mind that, in general, the support that we'll have in our initramfs for
*devices* will be quite poor as we are lacking **all** the kernel modules that
usually accompany the kernel (they live in /lib, we don't even have /lib yet!).
There are two ways to add driver support in an initramfs:

* Re-Compile the kernel with builtin drivers for what you need
* Provide the kernel object files (.ko) and all the required dependencies in
  paths expected by the kernel.

I opted with copying the .ko files around for now.

For network connectivity, it starts getting a bit specific with regards of
what type of NIC you'll have installed, but for now we'll continue with the
`e1000`, the generic driver that you can use with `qemu`.

Find and copy the required kernel module:

```
$ find /lib -path "*$(uname -r)*" -name e1000.ko
/lib/modules/5.0.0-27-generic/kernel/drivers/net/ethernet/intel/e1000/e1000.ko
```

Once that file is present (in the same path!) in your initramfs, you should be
able to run (adjusted for your network setup..)

```
modprobe e1000
ifconfig eth0 192.168.2.33 netmask 255.255.255.0 up
route add default gw 192.168.2.1
```

and be pingable! without even a disk!

While having a network is a big step forward, we still need some kind of
software that will allow us to download files. I did not think too much about
this and went with cURL, but maybe wget or some other tool would've been easier.

As with busybox, [clone curl](git@github.com:curl/curl.git) and build it to get
a static binary:

```
./buildconf
./configure --disable-shared
make curl_LDFLAGS=-all-static
```

which will give you a static `curl` binary.

Ok, we have networking support, we have curl, now we have to manually set up
the network device:

```
mkdir /etc /proc /sys
mount -t proc proc /proc
mount -t sysfs sysfs /sys
modprobe e1000

ifconfig eth0 192.168.2.33 netmask 255.255.255.0 up
route add default gw 192.168.2.1
echo "nameserver 192.168.2.1" > /etc/resolv.conf
```

and adjust our `kvm` invocation to also pass in a network device:

```
kvm -kernel /boot/vmlinuz-$(uname -r) -initrd initramfs.igz  -m 512 -cpu host -append quiet  -device e1000,netdev=net0,mac=DE:AD:BE:EF:88:39 -netdev tap,id=net0
```

![](/images/linux_flashing/3_networking_but_no_dns.png)

Why is DNS not working? Because it's provided by shared objects and we don't
have them in our initrd!

If we had been paying attention to the build, it did warn us about it:

```
curl_addrinfo.c:(.text+0x203): warning: Using 'getaddrinfo' in statically linked applications requires at runtime the shared libraries from the glibc version used for linking
```

A great way to avoid this, is to build a DNS resolver right into curl,
conveniently, curl supports ares so that means that adding `--enable-ares`
to the `configure` call solves  our problem:

![](/images/linux_flashing/4_networking_with_dns.png)

and again, we can make this happen with very few files:

```
$ find initramfs/ -type f
initramfs/curl
initramfs/lib/modules/5.0.0-27-generic/kernel/drivers/net/ethernet/intel/e1000/e1000.ko
initramfs/init
initramfs/busybox
```

You can find the example [here](https://gitlab.com/davidventura/flash-hdd-over-network/tree/master/3-useful-initramfs).


# Flashing a hard drive from initramfs

We are at the last step! We can now download a file from the network so let's
write it to disk, we only have to add a few things to the last `init`:

```
/curl http://david-pc.labs:8000/newfs.img --output newfs.img
echo 'Downloaded.. flashing'
dd if=newfs.img of=/dev/sda bs=1M conv=notrunc
echo 'Done!'
exec sh
```

but now, we need to pass a disk to kvm so it has a place to write to, we can do
so by appending  `-drive file=test-disk.img,format=raw` to the kvm invocation.

Creating the `test-disk.img` file is easy: just write a lot of zeroes to it: `dd
if=/dev/zero of=test-disk.img bs=1M count=1000`

*Keep in mind that this is an initial***ram***filesystem*, your virtual machine
must have enought **ram** assigned to it to keep the entire filesystem image in
memory.


Now.. the image is complaining that /dev/sda does not exist, and indeed, poking
at /dev/ shows that no devices were automatically created. Of course not!
There's no udev in this system.. this mechanism can get triggered by running
`mdev` (from busybox)

![](/images/linux_flashing/5_0_disk_missing.png)
With the disk block device ready, we can run the disk flashing from initramfs
![](/images/linux_flashing/5_disk_flashed.png)

Disk is flashed. We can't just reboot -- we'll boot straight back into the
initramfs, so we have to tweak our `kvm` invocation to not use the `initrd` for
booting:
`kvm -m 2048 -cpu host -device e1000,netdev=net0,mac=DE:AD:BE:EF:88:39 -netdev tap,id=net0  -drive file=test-disk.img,format=raw`
![](/images/linux_flashing/5_1_disk_booting.png)
Grub !
![](/images/linux_flashing/5_2_disk_booted.png)
TTY login!

Everything worked great!

You can find the example [here](https://gitlab.com/davidventura/flash-hdd-over-network/tree/master/4-write-image-to-disk).

# Booting into the new system without re-booting

To have this behave exactly as I want, I'd also like to remove the intermediate
reboot step after flashing.. after all, the same kernel is loaded, why do we
need to power cycle?

There are a few gotchas though, after flashing the disk, the kernel does not
know that we have a new partition table, and we can tell it by running
`partprobe /dev/sda`, which will print the new partition in the kernel logs
(`/dev/sda1`).

Even though the kernel knows about `/dev/sda1`, there's no block device
representing it in `/dev`, so we have to run `mdev` again, now `/dev/sda1`
exists!

We try to mount it and..

![](/images/linux_flashing/6_pivot_failure.png)

`Invalid argument`?

Let's try specifying the filesystem:

```
/ # mount -t xfs /dev/sda1 /newroot/
mount: mounting /dev/sda1 on /newroot/ failed: No such device
```

Wait.. does this kernel know about xfs? Let's check the configuration options
in the original machine that 'donated' this kernel:

```
$ grep XFS /boot/config-$(uname -r)
CONFIG_XFS_FS=m
```

Aha! It's a module. Let's add this module as well and try again:

```
xfs_ko=$(find /lib/modules/$(uname -r) -name xfs.ko)
mkdir -p initramfs/$(dirname $eth_ko) initramfs/$(dirname $xfs_ko)
cp $eth_ko initramfs/$(dirname $eth_ko)
```

and then we add `modprobe xfs` to our init, but no dice:

```
modprobe: module 'libcrc32c' not found
modprobe: 'kernel/fs/xfs/xfs.ko': unknown symbol in module or invalid parameter
```

this kernel module has dependencies! let's check on the dev machine what they
are:

```
$ lsmod | head -1; lsmod | grep -i xfs
Module                  Size  Used by
xfs                  1232896  0
libcrc32c              16384  3 nf_conntrack,nf_nat,xfs
```

so, we need libcrc32c as well and we'll add it in the exact same way that we
added `xfs`.

This is it! We are done! We can download and flash a golden disk image over the
network, and pivot into it within 20 seconds!

You can find the example [here](https://gitlab.com/davidventura/flash-hdd-over-network/tree/master/5-boot-into-system-without-reboot).

# Results

You can see the results here (click the image to watch the asciicast):

<asciinema-player src="/casts/linux_flashing.cast" cols="80" rows="31" preload=""></asciinema-player>

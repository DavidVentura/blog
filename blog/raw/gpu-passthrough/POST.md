This is a recompilation of various sources to get gpu passthrough on Debian.

# Update your kernel
For amd you need at least 4.14.\*, or the npt patch. After that update your initramfs again. (Is that necessary?)

# BIOS/UEFI
Enable IOMMU and Virtualization

# Modules
## disable modules

`/etc/modprobe.d/passthrough-blacklist.conf

```
blacklist radeon
blacklist amdgpu
blacklist snd_hda_intel
```

## Load modules

`/etc/modules`

```
vfio
vfio_iommu_type1
vfio_pci
vfio_virqfd
```
## set vfio-pci options

`/etc/modprobe.d/vfio.conf`

```
options vfio-pci ids=1002:67ef,1002:aae0,13f6:8788 disable_idle_d3=1
```

# set grub parameters
`/etc/default/grub`

```
GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt cgroup_enable=memory rootdelay=2 swapaccount=1 text"
```

run `update-grub2`

# edit initramfs

`/etc/initramfs-tools/modules`

```
vfio
vfio_iommu_type1
vfio_pci ids=1002:67ef,1002:aae0,13f6:8788 disable_idle_d3=1
vfio_virqfd
vhost-net
```

run `update-initramfs -u`



# KVM

My script looks like this

```
taskset -c 12-15 ./qemu-patched \
        -enable-kvm -m 8192 \
        -cpu host -smp 4,sockets=1,cores=4,threads=1 \
        -bios /usr/share/ovmf/OVMF.fd -vga none -nographic \
        -serial none -parallel none \
        -netdev type=tap,id=net0,ifname=vmtap0,vhost=on \
        -device virtio-net-pci,netdev=net0,mac=00:16:3e:00:02:02 \
        -device vfio-pci,host=0b:00.0,multifunction=on,romfile=$USR_HOME/scripts/rx560.rom \
        -device vfio-pci,host=0b:00.1 \
        -device vfio-pci,host=0d:00.3 \
        -drive id=disk0,if=virtio,cache=none,file=$DISK,format=qcow2 \
        -rtc clock=host,base=utc;
```

# GPU Bios

If you get a black screen when you boot your VM and get a core stuck to 100% you might have a 'bad' gpu bios. You need to extract your BIOS from your own card, if you use linux you need to have 2 GPUs or otherwise you get a corrupt image. On windows this works fine.

# Bugs

## Device or resource busy

I got spammed to death with `qemu-system-x86_64: vfio_region_write(0000:0a:00.0:region0+0x11d9e4, 0x3a4c4c,4) failed: Device or resource busy` which was fixed by running

```
echo 0 > /sys/class/vtconsole/vtcon0/bind
echo 0 > /sys/class/vtconsole/vtcon1/bind
echo efi-framebuffer.0 > /sys/bus/platform/drivers/efi-framebuffer/unbind
```

# Useful testing scripts

This was all taken from the arch wiki and formatted / made a bit nicer

##  Test your IOMMU groups
 
```bash
#!/bin/bash
shopt -s nullglob
for d in /sys/kernel/iommu_groups/*/devices/*; do 
    n=${d#*/iommu_groups/*}; n=${n%%/*}
    printf 'IOMMU Group %s ' "$n"
    lspci -nns "${d##*/}"
done | sort -n -k3
```

You'll most likely have success passing devices that are on their own on a given IOMMU group.  
I couldn't get any device which wasn't on his own passed to KVM, maybe you could try the `acs override patch`.

## Test your USB hubs

```bash
for usb_ctrl in $(find /sys/bus/usb/devices/usb* -maxdepth 0 -type l); do
        pci_path="$(dirname "$(realpath "${usb_ctrl}")")";
        echo "Bus $(cat "${usb_ctrl}/busnum") --> $(basename $pci_path) (IOMMU group $(basename $(realpath $pci_path/iommu_group)))";
        lsusb -s "$(cat "${usb_ctrl}/busnum"):";
        echo;
done
```

This was useful for me to test in which hub I had my devices, as one of my root hubs was OK to be passed to the VM.

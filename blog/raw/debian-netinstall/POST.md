So far, anything that I've deployed in my lab has been running in a container,
but when I wanted to deploy a VM I realized that I had to click through the
debian netinstall and likely forget about the settings in the future.  
After some investigation I remembered the classic *preseeding* method.

## Preseeding

This method consists in pre-selecting all the answers required for the debian
installer. It is a bit shitty that I am not simply using a base image and 
re-generating the ssh-keys and hostname on first boot, but this is widely
supported as far as I know.

### Choosing the presets
Presets are quite straight-forward, the customized values are:

* Locale (keyboard, language)
* Apt mirror & proxy
* Disk partitioning

An interesting gotcha was that this uses */dev/vda* and the defaults and docs
always talk about */dev/sda*; I did not know that this would be */dev/vda* when
using qemu, so it took me a while to figure out why the installer was complaining
about an invalid rootfs.


```
# US locale/kbd map
d-i debian-installer/locale string en_US
d-i keyboard-configuration/xkb-keymap select us

# automatically select network interface
d-i netcfg/choose_interface select auto

# set host and domain
d-i netcfg/get_hostname string debian-pxe
d-i netcfg/get_domain string localdomain

# disable WEP dialogue
d-i netcfg/wireless_wep string

# use http.us.debian.org as mirror with no proxy
d-i mirror/country string manual
d-i mirror/http/hostname string ftp.nl.debian.org
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string  http://proxies.labs:3142

# don't make a regular user / set root password
d-i passwd/make-user boolean false
# mkpasswd -m sha-512 <pwd>
d-i passwd/root-password-crypted password $6$HDEYl/aS5d$LPmzSLK2rvbvA8C5HjavBTST8XZrXPAu2P6EPgnB5RPxpWDhrnDk7qouJ.0XSSWAeEFyl459m2zwj1N1D2NPL1

d-i clock-setup/utc boolean true
d-i time/zone string Europe/Amsterdam
d-i clock-setup/ntp boolean true

### Partitioning

# use lvm partitioning
d-i partman-auto/method string lvm
d-i partman-lvm/device_remove_lvm boolean true
d-i partman-lvm/confirm boolean true
d-i partman-lvm/confirm_nooverwrite boolean true

# make lvm the max size
d-i partman-auto-lvm/guided_size string max
d-i partman-auto-lvm/new_vg_name string debian

# use the following partition scheme on /dev/vda
d-i partman-auto/disk string /dev/vda
d-i partman-auto/choose_recipe select boot-lvm

# /boot 500M ext4
# /var/log 500M ext4
# / 2G+ ext4
d-i partman-auto/expert_recipe string               \
    boot-lvm ::                                     \
        500 500 500 ext4                            \
            $primary{ } $bootable{ }                \
            method{ format } format{ }              \
            use_filesystem{ } filesystem{ ext4 }    \
            mountpoint{ /boot }                     \
        .                                           \
        500 500 500 ext4                            \
            $lvmok{ }                               \
            lv_name{ var_log } in_vg { debian }     \
            $primary{ }                             \
            method{ format } format{ }              \
            use_filesystem{ } filesystem{ ext4 }    \
            mountpoint{ /var/log }                  \
        .                                           \
        2048 2048 -1 ext4                           \
            $lvmok{ }                               \
            lv_name{ root } in_vg { debian }        \
            $primary{ }                             \
            method{ format } format{ }              \
            use_filesystem{ } filesystem{ ext4 }    \
            mountpoint{ / }                         \
        .

# remove any RAID partitioning
d-i partman-md/device_remove_md boolean true

# don't confirm anything
d-i partman-basicfilesystems/no_mount_point boolean false
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true
# disable swap warning
d-i partman-basicfilesystems/no_swap boolean false


# install standard system with ssh-server
tasksel tasksel/first multiselect standard, ssh-server

# also install the htop package
d-i pkgsel/include string htop

# upgrade all packages
d-i pkgsel/upgrade select full-upgrade

# disable popularity contest
popularity-contest popularity-contest/participate boolean false

# force grub install to /dev/vda
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true
d-i grub-installer/bootdev  string /dev/vda

# don't wait for confirm, just reboot when finished
d-i finish-install/reboot_in_progress note
```

### Booting the autoinstall

The easiest way to boot this automated setup is to simply go to *Advanced ->
Automated setup* in the wizard, then typing in the path to a webserver that
can provide this file.. but this defeats the point of automating the setup,
I will forget about the procedure in some time, and the webserver might stop
existing in the meantime.


### Baking the config into the image

It would be easier for me to not have to remember anything, and simply have
the config values baked into the image. Here are condensed instructions from
[the official docs](https://wiki.debian.org/DebianInstaller/Preseed/EditIso):

```bash
## Populate preseed.cfg with your defaults prior to this
mkdir -p isofiles
bsdtar -C isofiles -xf debian-9.9.0-amd64-netinst.iso 
gunzip isofiles/install.amd/initrd.gz
echo preseed.cfg | cpio -H newc -o -A -F isofiles/install.amd/initrd
gzip isofiles/install.amd/initrd
cd isofiles
md5sum $(find -follow -type f) > md5sum.txt
cd ..
genisoimage -r -J -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o preseed-debian-9.9.0-amd64-netinst.iso isofiles/
```


At this point, you've added your *preseed.cfg* into *debian-9.9.0-amd64-netinst.iso*,
creating *preseed-debian-9.9.0-amd64-netinst.iso*, but you **still** have to
go to *Advanced -> Automated setup* in the wizard (although you don't need to
type the webserver's address anymore).

## Automatically picking an entry from the menu

isolinux.cfg: set **timeout** to 1  
menu.cfg: remove all includes except **stdmenu.cfg** and **txt.cfg**  
txt.cfg: replace contents with  

```
label install
        menu label ^Install
        menu default
        kernel /install.amd/vmlinuz
        append vga=788 auto=true priority=critical file=/preseed.cfg initrd=/install.amd/initrd.gz --- quiet 
default install
```

Now, re-package the iso:
```bash
md5sum $(find -follow -type f) > md5sum.txt
cd ..
genisoimage -r -J -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o preseed-debian-9.9.0-amd64-netinst.iso isofiles/
```

## Source

You can find the script to apply these changes to an existing ISO in my [github](https://github.com/DavidVentura/preseed-debian-iso).

## Demo

You can take a look at a recording of an install with these values:  

<asciinema-player poster="/images/debian-installer.png" src="/casts/debian_netinstall.cast" cols="81" rows="31" preload=""></asciinema-player>

---
title: Debian stretch headless install
date: 2018-02-24
tags: debian, systems-deployment, homelab
description: 
---
This is my adaptation of [this](https://sowhatisthesolution.wordpress.com/2016/03/13/headless-debian-install-via-ssh/) for debian stretch.

Mount the iso and copy the contents for rw.

Change the menu to load SSH on boot by default, edit isonew/isolinux/gtk.cfg
(To see what file to edit in case of future changes you can run `grep "menu default" isolinux/*`)

I replaced the entire file with

```
default netinstall
label netinstall
    menu label ^Install Over SSH
    menu default
    kernel /install.amd/vmlinuz
    append auto=true vga=788 file=/cdrom/preseed.cfg initrd=/install.amd/initrd.gz locale=en_US console-keymaps-at/keymap=us
```

Generate isonew/preseed.cfg
```
#### Contents of the preconfiguration file
### Localization
# Locale sets language and country.
d-i debian-installer/locale select en_US
# Keyboard selection.
d-i console-keymaps-at/keymap select us
d-i keyboard-configuration/xkb-keymap select us
### Network configuration
# netcfg will choose an interface that has link if possible. This makes it
# skip displaying a list if there is more than one interface.
d-i netcfg/choose_interface select auto
# Any hostname and domain names assigned from dhcp take precedence over
# values set here. However, setting the values still prevents the questions
# from being shown, even if values come from dhcp.
d-i netcfg/get_hostname string newdebian
d-i netcfg/get_domain string local
# If non-free firmware is needed for the network or other hardware, you can
# configure the installer to always try to load it, without prompting. Or
# change to false to disable asking.
d-i hw-detect/load_firmware boolean true
# The wacky dhcp hostname that some ISPs use as a password of sorts.
#d-i netcfg/dhcp_hostname string radish
d-i preseed/early_command string anna-install network-console
# Setup ssh password
d-i network-console/password password install
d-i network-console/password-again password install
```

recreate `md5sum.txt`

```bash
chmod 666 md5sum.txt
find -follow -type f -exec md5sum {} \; > md5sum.txt
chmod 444 md5sum.txt
```

run inside `isonew/`

`xorriso -as mkisofs -b isolinux/isolinux.bin -c isolinux/boot.cat -iso-level 3 -no-emul-boot -partition_offset 16 -boot-load-size 4 -boot-info-table -o ../debian-9.3.0-amd64-headless.iso ../isonew/`

test with `kvm -m 512 -cdrom debian-9.3.0-amd64-headless.iso`

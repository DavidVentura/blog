I wanted to replace my pfSense VM with a dedicated router so I could take my homelab offline without losing internet connectivity, so I bought an Espressobin


# Basic setup

## Get your ram configuration
Connect the espressobin with the supplied micro usb cable and connect to the serial device that pops up. In my case I used `screen` to connect to `/dev/ttyUSB0` and got greeted by the following prompt:

```
...
DDR_TOPOLOGY is 4 :     DDR3, 1CS 1G
...
Model: Marvell Armada 3720 Community Board ESPRESSOBin
       CPU    @ 1000 [MHz]
       L2     @ 800 [MHz]
       TClock @ 200 [MHz]
       DDR    @ 800 [MHz]
DRAM:  1 GiB
...
```

## Download correct U-Boot image

For my initial testing I wanted to use Debian, but as there is no current image available I'll just use armbian.

Download your image from [Here](https://dl.armbian.com/espressobin/u-boot/) and put it in a FAT-formatted usb drive.

Run `bubt flash-image-MEM-RAM_CHIPS-CPU_DDR_boot_sd_and_usb.bin spi usb`, then `dd` the armbian image to the same usb drive and run

```
setenv initrd_addr 0x1100000
setenv image_name boot/Image
setenv load_script 'if test -e mmc 0:1 boot/boot.scr; then echo \"... booting from SD\";setenv boot_interface mmc;else echo \"... booting from USB/SATA\";usb start;setenv boot_interface usb;fi;if test -e \$boot_interface 0:1 boot/boot.scr;then ext4load \$boot_interface 0:1 0x00800000 boot/boot.scr; source; fi'
setenv bootcmd 'run get_images; run set_bootargs; run load_script;booti \$kernel_addr \$ramfs_addr \$fdt_addr'
saveenv
```

(This all came from [here](https://www.armbian.com/espressobin/).)

# Fancy stuff

Being able to run `tcpdump` on my router allowed me to investigate and map my network. I wrote a script to dectect connections going to the internet and to my 'old' (192.168.1.0/24) network.

I'll come back to this in a post dedicated to monitor the network.

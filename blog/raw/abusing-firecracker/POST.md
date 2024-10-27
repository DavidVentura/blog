---
title: Spawning VMs for unreasonable workloads
date: 2024-10-01
tags: rust, firecracker, linux, shitpost, short
slug: abusing-firecracker
description: Running VMs just because it's quick and easy
---

Some time ago, I forked [Firecracker](https://github.com/firecracker-microvm/firecracker/tree/main) for some experiments and realized
you can spawn networked a VM in [as little as 6 milliseconds](/posts/minimizing-linux-boot-times/), fully programmatically.

The idea here is that you can [programmatically](https://github.com/DavidVentura/firecracker-spawn) start a VM with:

- Any program which you wish to run as root.
- Any kernel
- A set of block devices (can use files)

The spawning of the VM looks something like this:

```rust
let v = Vm {
	vcpu_count: 1,
	mem_size_mib: 32,
	kernel_cmdline: "panic=-1 reboot=t init=/goinit".to_string(),
	kernel_path: PathBuf::from("vmlinux-mini-net"),
	rootfs_path: PathBuf::from("rootfs.ext4"),
	rootfs_readonly: false,
	extra_disks: vec![],
	net_config: Some(NetConfig {
		tap_iface_name: "mytap0".to_string(),
		vm_mac: None,
	}),
};
v.make().unwrap();
```

The only downside is that you need to be root (or member of `kvm` + setting up a tap interface)

For someone more creative, super-fast VM creation would've spawned many ideas for new tools, but I've only managed to come up with four:

## Populating filesystem images

Somehow the only ext4/btrfs/xfs implementations live in the kernel, requiring you to mount disk images to modify them, which is _barbaric_. 

I wrote a tool, creatively named [fs-writer](https://github.com/DavidVentura/rootless-filesystem-management), which will unpack a `tar` file onto a file containing a xfs/ext4/btrfs filesystem (which you can create without root, using `mkfs.<fs>`)

```
# Count entries on tar file
$ tar tvf disk.tar.gz | wc -l
5283

# Unpack without root! (but you gotta be member of `kvm`)
$ fs-writer --in-file disk.tar.gz --out-fs output.ext4 --pad-input-with-zeroes -vvv
2024-02-16T10:07:30.368Z DEBUG [fs_writer] Initializing
2024-02-16T10:07:30.368Z DEBUG [fs_writer] Unpacking kernel
2024-02-16T10:07:30.408Z DEBUG [fs_writer] Identifying target fs
2024-02-16T10:07:30.408Z DEBUG [fs_writer] Detected ext4 as output
2024-02-16T10:07:30.408Z DEBUG [fs_writer] Unpacking bootstrap rootfs
2024-02-16T10:07:30.409Z INFO  [fs_writer] Starting VM
2024-02-16T10:07:30.427Z TRACE [fs_writer] Setting up environment
2024-02-16T10:07:30.427Z TRACE [fs_writer] Mounting filesystem
2024-02-16T10:07:30.429Z TRACE [fs_writer] Unpacking payload
2024-02-16T10:07:30.518Z INFO  [fs_writer] Success

$ # validate it unpacked
$ sudo mount output.ext4
$ sudo find output.ext4 | wc -l
5283
```

The compiled binary embeds a Linux kernel (build config at artifacts/kernel-config) and a "bootstrap" initrd, which will unpack the source tar.gz file into the destination filesystem and exits.

Alternative init ramdisks (eg: to unpack different formats) can be provided with --alternative-initrd.

## Extreme CGI-Bin

or "peak web development".

Once upon a time, we had [CGI-Bin](https://en.wikipedia.org/wiki/Common_Gateway_Interface) as means of interacting with incoming requests: when a request came in, the HTTP server started a new process to deal with it.

Each process only lived as long as the request, which meant no persistent state, and no bugs from stale resources or memory leaks. In this regard modern stacks suck -- they run for longer than the requests and even have persistent state! What if we could change that? 

We could _even_ give the webserver a name consisting of a single greek letter. Maybe Omega? That one comes way after lambda.

[This project](https://github.com/DavidVentura/extreme-cgi-bin) doesn't do anything crazy - it starts up a TCP socket, and on any connection, it will spawn a micro-vm and forward the connection to it, something like this:

{embed-mermaid assets/http.mermaid}

Now, each of these requests needs to wait a whole kernel boot and for the webserver to start up (a "cold start") -- which averages around 14ms on my system. what if, WHAT IF, we could pre-spawn a bunch of VMs and have them ready for the clients? Could even call it `pre-spawn`.

## Docker without docker

... Only to get to use the name "faux-cker".

Unpack the image, then convert it to cpio:

```bash
$ docker create hello-world
c32eb303e8c7c372195a54c618c8ae9c77a99f0d169a0f577fd224342bcdf027
$ docker export c32eb303e8c7c372195a54c618c8ae9c77a99f0d169a0f577fd224342bcdf027 -o out.tar
$ tar xvf ./out.tar 
.dockerenv
dev/
dev/console
dev/pts/
dev/shm/
etc/
etc/hostname
etc/hosts
etc/mtab
etc/resolv.conf
hello
proc/
sys/
$ ~/git/tar2cpio/target/debug/tar2cpio out.tar > out.cpio
```

and boom[^lame], you can run any container directly as a VM.

[^lame]: Okay, this one is kinda lame, I didn't actually finish writing this tool, and I've delayed this write-up for 7 months, thinking I'd eventually get around to it, but honestly, I won't.

## Running tests

The only non-joke function I found for this was integration tests; which led me to write [firetest](https://github.com/DavidVentura/firetest)[^firetest-name], which will run whatever you pass it as an argument inside a VM:

Some examples:

```bash
$ ./firetest busybox ls -lh /
total 2M     
-rwxrwxrwx    1 0        0           1.0M Oct  1 20:30 busybox
drwxr-xr-x    2 0        0            100 Oct  1 20:30 dev
-rwxrwxrwx    1 0        0         605.6K Oct  1 20:30 init
dr-xr-xr-x   68 0        0              0 Oct  1 20:30 proc
drwx------    2 0        0             40 Oct  1 20:30 root
dr-xr-xr-x   11 0        0              0 Oct  1 20:30 sys
```

```bash
$ ./firetest busybox uname -a
Linux (none) 6.7.3 #225 Mon Sep 30 07:41:27 UTC 2024 x86_64 GNU/Linux
```
A more interesting example, running `cargo test` (the resulting binaries) in these VMs:

```
$ ./firetest target/x86_64-unknown-linux-musl/debug/deps/integration_test-8b86d294da2872d3
running 4 tests
test trace_direct_connection ... ok
test trace_ipvs_connection_accepted ... ok
test trace_ipvs_connection_not_responding ... ok
test trace_ipvs_connection_refused ... ok
```

Some interesting properties for `firetest` are:
- Speed: These run in ~200ms
- Self-contained: Single binary includes a kernel, and unpacks strace + busybox into the initramfs for debugging
    - There are no requirements for your payload, but also, nothing is done for it (eg: /dev/ is empty, call `/busybox mdev -s` if you want it populated)

[^firetest-name]: vmtest inspired this tool, hence the name

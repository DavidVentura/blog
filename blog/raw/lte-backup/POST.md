---
title: Homelab backup LTE connection
date: 2024-03-15
tags: homelab, wireguard
slug: homelab-backup-lte-connection
description: Setting up a wireguard backup tunnel over LTE
---

For quite a while I wanted to set up a backup connection into my homelab — at least _once_ the router has dropped its DHCP lease when I was away and 
I had no way of fixing it.

Ideally, I'm never going to access the lab via this network, so I didn't want to have a monthly subscription for data I was probably not going to use.

I found a bunch of vendors that'd sell you a SIM which is valid for 1 year, but most of them required a VAT number, so they'd only sell to business.

Finally I found [droam](https://droam.com/) which sells to individuals and bought a [2GB prepaid SIM](https://droam.com/products/prepaid-data-sim-card) for €20.

To go with it, I bought a USB 4G modem, the ZTE MF79U.

Upon plugging in the modem, an ethernet interface showed up.

## Basic setup
To set up the modem, I initially configured the interface in DHCP mode, as I didn't know in which subnet the modem itself was configured

Placing the following config into /etc/network/interfaces

```
auto enx344b50000000
iface enx344b50000000 inet dhcp
```

After running `ifup enx344b50000000`, the interface came up on `192.168.0.2/24`; I brought it down by running `ifdown enx344b50000000` and re-configured it in static mode:

```
auto enx344b50000000
iface enx344b50000000 inet static
        address 192.168.0.2
        netmask 255.255.255.0
        gateway 192.168.0.1
```

I prefer a static config, as fewer things can go wrong, but also, my `dhclient` config would overwrite my DNS configuration otherwise, making all DNS queries go over the LTE interface.

With the interface up, I assumed I'd be able to configure the modem with a browser, so I set up an SSH tunnel to my router to access it
```
ssh -D 1337 -q -N router
```

I use [FoxyProxy](https://github.com/foxyproxy/browser-extension) to configure rules, so that only the LTE subnet is proxied via the router.

With the proxy set up, I was greeted by this lovely message:

<center>![](/images/lte-backup/policy.png)</center>

The auto-update feature is _enabled by default_, which seems crazy to me. Pressing REJECT just logs you out.

I clicked a bunch on the settings, disabling the auto-update feature, DHCP server and Wifi access point.

## Testing the interface

```bash
$ ping -I enx344b50000000  1.1.1.1
PING 1.1.1.1 (1.1.1.1) from 192.168.0.2 enx344b50000000: 56(84) bytes of data.
^C
--- 1.1.1.1 ping statistics ---
2 packets transmitted, 0 received, 100% packet loss, time 28ms

```

Looking at the kernel logs (`dmesg`) I see that all the packets are getting dropped

```
IPv4: martian source 192.168.0.2 from 78.46.233.xx, on dev enx344b50000000
```

A packet is considered [martian](https://datatracker.ietf.org/doc/html/rfc1812#section-5.3.7) if it arrives on an unexpected interface; looking at the routing table

```bash
$ ip route
default via 178.69.69.1 dev wan 
192.168.0.0/24 dev enx344b50000000 proto kernel scope link src 192.168.0.2 
```

the kernel expects a packet with `src=1.1.1.1` to come from `wan`:

```bash
$ ip route get 1.1.1.1
1.1.1.1 via 178.69.69.1 dev wan src 178.69.69.239 uid 0 
```

To allow for reply packets coming on non-optimal interfaces, I set the reverse-path filtering policy to "loose" with a sysctl setting:

```bash
$ sysctl -w net.ipv4.conf.enx344b50000000.rp_filter=2
```

and now it can successfully ping the internet.

## Configuring Wireguard

As the LTE interface is behind a NAT which I don't control, it can only be an initiator in a Wireguard connection.

The goal is to _only_ route packets from the VPN through the interface, we can do this by:

```bash
# Create a routing table which defaults to the LTE interface
ip route add default via 192.168.0.1 dev enx344b50000000 table 123

# Create a rule to move any IP packet tagged as coming from Wireguard into the "LTE" routing table
ip rule add fwmark 0x7b table 123
```

Now Wireguard needs to [mark](https://tldp.org/HOWTO/Adv-Routing-HOWTO/lartc.netfilter.html) all packets, which can be achieved with

```ini
[Interface]
FwMark = 0x7b
```

Now, testing from my VPS I can connect over the LTE link (the non-LTE connection has ~25ms of latency).

```
$ ping 10.88.88.1
PING 10.88.88.1 (10.88.88.1) 56(84) bytes of data.
64 bytes from 10.88.88.1: icmp_seq=1 ttl=64 time=122 ms
64 bytes from 10.88.88.1: icmp_seq=2 ttl=64 time=192 ms
64 bytes from 10.88.88.1: icmp_seq=3 ttl=64 time=128 ms
64 bytes from 10.88.88.1: icmp_seq=4 ttl=64 time=127 ms
```

## NAT

I left the interface up and came back to check the next day, to my surprise, I could not ping the LTE modem anymore over the Wireguard connection.

I assume that as these 4g connections are NAT'd, the conntrack rule expired and my packets started getting dropped.

Luckily, Wireguard has a feature to work around this very thing, sending keep-alive messages on an interval.

I experimented with the highest value that wouldn't drop my connection and settled with

```
PersistentKeepalive=80
```

Which boils down to something like 1KB/hour =~ 10MB/year.

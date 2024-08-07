---
title: BSD inspired network setup
date: 2019-09-22
tags: networking, homelab
description: I replaced my home dnsmasq with nsd, unbound and dhcpd for a more reliable environment.
---

For quite some time, I've been running a dnsmasq instance on my router that was
acting as:

- DHCP server
- DNS forwarder
- DNS caching
- DNS-based ad-blocking
- Authoritative name server
- TFTP server (wtf dnsmasq)

After watching EuroBSDCon 2019 I got inspired to try the BSD approach to network
services.

The new system looks something like this:

```
+----------+                     +--------+
|          |                     |        |
| clients  +-------------------->| dhcpd  |
|          |                     |        |
+----+-----+                     +--------+
     |                               |
     |                               v
     |         +------------+    +--------+
     |         |            |    |        |
     +-------->|  unbound   |--->|  nsd   |
               |            |    |        |
               +------------+    +--------+
```

## DHCP

For most clients, when they connect to the network they will make a DHCP request
with dhcpd, and if they provide a name (or are present in
the list of MAC-address-to-name mapping), their name and IP address will be
added to a local zone in nsd, so that it can be resolved by the other clients.
This is particularly handy for things like the set-top box.

Getting client hostnames into the network's DNS was a feature of dnsmasq, but 
it is not provided by default by the bsd standard utilities, although it is easy
to accomplish as both dhcpd and nsd are well suited for a bit of scripting.

dhcpd provides three events: commit, release and expiry. For my usecase,
executing a script on commit is enough.

```
on commit {
    set clhost = pick-first-value(
          host-decl-name,
          option fqdn.hostname,
          option host-name,
          "none");
    set clip = binary-to-ascii(10, 8, ".", leased-address);
    execute("/root/add_or_update_entry.sh", clip, clhost);
}
```

Which then shows in the logs as

```
DHCPDISCOVER from 5c:cf:7f:d7:0d:95 (RFPOWER) via lan0
DHCPOFFER on 192.168.2.102 to 5c:cf:7f:d7:0d:95 (RFPOWER) via lan0
data: host_decl_name: not available
execute_statement argv[0] = /root/add_or_update_entry.sh
execute_statement argv[1] = 192.168.2.102
execute_statement argv[2] = RFPOWER
```

The actual script to update nsd is also similarly simple (although it does not
handle expiry/release at all), it boils down to:

```
if [ -z "$found" ]; then
	echo $entry >> $zone_file
else
	sed -i "s|^$name.*|$entry|" $zone_file
fi

nsd-control reload "$zone_name"
```

## DNS

Once clients have an IP address (either static or provided by dhcpd), they will
start making requests to resolve domain names to unbound. Most queries will be
resolved via the root name servers, and a very small subset of those will be either:

1. Local client request (for the .labs domain)
2. Targeted at my public domain (davidventura.com.ar)

Those special requests, are handled by a special zone; they are not sent to the
root name servers.

The local domain `.labs` hosts a combination of statically provided domains (for
servers) and it also gets updated with dhcpd entries.

For the public domain, I have set up internal A records, as it's way easier to access
the services I host always by the same domain.  As I also have some subdomains
on actual public IPs, I had to also specify those.  

```
de                               IN A 78.46.233.60
healthchecks                     IN A 78.46.233.60
davidventura.com.ar.             IN A 192.168.50.101
*                                IN A 192.168.50.101
```

## Blocking Ads

There's another (set of) special zone(s), a big list of 'bad' domains is
specified to be marked as `rejected` forever; this is a neat mechanism to block
undesirable domains (mostly ads, but also a good chunk of facebook's and
google's domains).

An entry in the blocklist looks like this:

```
local-zone: "101com.com" refuse
```

It is trivial to `wget` a bunch of the blocklists that can be found on the
internet and adapt them to this format, even so, pay attention and avoid
duplicate entries, otherwise unbound will not start.

## Privacy concerns

Now that I am no longer forwarding my requests, there's another privacy concern
popping up: my IP address and my queries are now exposed to all the nameservers,
while before it was only exposed to google/cloudflare/etc.  
For the moment, I feel like this is a reasonable tradeoff. We'll see.

## Sources

[Blocking ads 1](https://www.tumfatig.net/20190405/blocking-ads-using-unbound8-on-openbsd/)  
[Blocking ads 2](https://www.wilderssecurity.com/threads/adblocking-with-unbound.406346/)  
[Blocking ads 3](https://etherarp.net/build-an-adblocking-dns-server/)  
[NSD Tutorial](https://calomel.org/nsd_dns.html)  
[Unbound Tutorial](https://calomel.org/unbound_dns.html)  
[DHCP hostname into DNS](https://www.linuxquestions.org/questions/linux-networking-3/dhcpd-getting-client-provided-hostname-in-execute-script-4175451000/)  
[DNS Script idea](https://jpmens.net/2011/07/06/execute-a-script-when-isc-dhcp-hands-out-a-new-lease/)  

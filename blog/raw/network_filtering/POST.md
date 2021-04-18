---
title: Network update part 4: Proxies
date: 2018-05-28
tags: networking
incomplete: True
description: 
---
While [segregating my network](https://blog.davidventura.com.ar/network-update-part-3-network-segregation.html) I ran into a few 'issues'; certain (mostly) LAN-only services required internet access to work! As a workaround I gave them internet access (temporarily) while I figured out how to best deal with the issue.

My main requirement was being able to restrict http/s traffic based on domain (not IP). Turns out, a lot of proxies have this functionality, and after looking around for a bit I opted for `tinyproxy` because:

* It's on the Debian repos
* It has low footprint
* It can do domain whitelisting

Plus, I needed to MITM SSL sites (for filtering) so I'm using `stunnel`.

## Deploying and configuring tinyproxy + stunnel

For deployment I simply added `tinyproxy` and `stunnel` to my ansible package list for the `proxies` host (this host also runs apt-cacher-ng and tcpproxy), which is in the DMZ.
 
Tinyproxy config

```
User tinyproxy
Group tinyproxy
Port 8888
Timeout 600
DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
Logfile "/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
PidFile "/run/tinyproxy/tinyproxy.pid"
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0
Allow 127.0.0.1
ViaProxyName "tinyproxy"
Filter "/etc/tinyproxy/filter"
FilterURLs Off
FilterExtended On
FilterDefaultDeny Yes
ConnectPort 443
ConnectPort 563
```

From the defaults I changed:

* Whitelist instead of Blacklist
* Enable proxy filtering
* Set the filtering to be based on domains instead of URLs

`filter` file

```
github.com
java.sun.com
maven.apache.org
springframework.org
#FIXME
twitch
letsencrypt
```

## Create ssl cert

```
openssl genrsa -out host_files/proxies/key.pem 4096
openssl req -new -x509 -key host_files/proxies/key.pem -out host_files/proxies/cert.pem -days 1826
```

### Updating firewall

### Setting HTTP proxy for other servers

I (unsuprisingly!) ran into some issues, even though in theory everything should be OK:

* Certain devices don't give a shit. Chromecast ignores the NTP server assigned by the DHCP server.
* Madsonic (service I use to self host music) requires internet access to start (!!). They are downloading `xsd` files from  both `springframework.org`, `maven.apache.org` and `java.sun.com`. Without these files, Madsonic refuses to start. After this issue I'll look for another music player.
* I am currently having an issue routing from `rproxy` (VLAN 20) to the physical server on it's untagged interface.
  * If I connect from `rproxy`(20) to server(20) then it works fine (via the linux virtual bridge, never reaches the router)
  * Otherwise packets are being dropped, even though the router sees them.

## "Fixes"

### NTP for chromecast:

```
DNAT        wifi    loc:192.168.2.1             udp    123
```

I just map any NTP request coming from `wifi` to my NTP server

### Unable to route

I added IP for the physical server (VLAN 20) in `/etc/hosts` for the `rproxy` container, which makes it "work".

## Pending issues

I left quite a lot of things with access to the internet, I'll write a follow up post detailing how I closed each one of them. For now the list is:

* Jenkins: ssh out, used to update git repos. http out: used by a Docker image to put images in S3.
* Madsonic (detailed above)
* Sonarr http out
* Twitch http out (this is a custom twitch broadcaster I wrote so I can watch the same stream all over the house)
* Router has full internet access (testing + repositories)
* Grafana is trying to reach `grafana.com` (http) looking for updates for plugins or somesuch.
* Pip is broken on all hosts!
* `Books` cannot connect to IRC anymore.

### Possible solutions

* For HTTP I'll use a simple proxy which will be in the DMZ (Also useful for pip).
* For SSH I'll simply add a `tcpproxy` instance which will map 1:1.
* I'll have to investigate the IRC protocol to proxy it (and DCC) which is core for my `books` setup.

After adding a [fancy router](https://blog.davidventura.com.ar/network-update-part-1-custom-router-with-espressobin.html) to my setup and adding some [monitoring](https://blog.davidventura.com.ar/network-update-part-2-monitoring-the-network-with-netflow-influxdb-and-grafana.html) I decided I could segregate my network, as the current state was just bunching everything on the common VLAN.

New setup:

![](images/network_post.png)

You can find the fancy DOT file [here](https://raw.githubusercontent.com/DavidVentura/blogging_like_its_2017/master/blog/raw/network_monitoring/network_post.dot).

The main idea was to segregate devices that do not need to talk to each other to avoid potential security risks. Most stuff is in the 'server' VLAN now, and it doesn't really make sense to access it directly, as we have access via an nginx reverse proxy that does SSL termination.

My first step was to first move everything into their respective VLANs:

# Creating interfaces

On the router I simply added these lines to my `/etc/network/interfaces` file

```
iface lan0.10 inet static
        address    192.168.10.1
        netmask    255.255.255.0

iface lan0.20 inet static
        address    192.168.20.1
        netmask    255.255.255.0

iface lan0.30 inet static
        address    192.168.30.1
        netmask    255.255.255.0

iface lan0.40 inet static
        address    192.168.40.1
        netmask    255.255.255.0

iface lan0.50 inet static
        address    192.168.50.1
        netmask    255.255.255.0
```

and ran `ifup` for every interface.

On the server I added something similar (but with bridges):

```
# wifi
iface enp8s0.10 inet manual

auto vmbr10
iface vmbr10 inet static
        address  192.168.10.10
        netmask  255.255.255.0
        gateway  192.168.10.1
        bridge_ports enp8s0.10
        bridge_stp off
        bridge_fd 0
        bridge_vlan_aware yes
        nameserver      192.168.10.1

```
(repeated 5 times with matchin VLANs)

# Router configuration

In the shorewall `interfaces` file I added:

```
wifi    lan0.10         dhcp,tcpflags=0,nosmurfs
srv     lan0.20         dhcp,tcpflags=0,nosmurfs
guest   lan0.30         dhcp,tcpflags=0,nosmurfs
bnet    lan0.40         dhcp,tcpflags=0,nosmurfs
dmz     lan0.50         dhcp,tcpflags=0,nosmurfs
```

In the `snat` file I also added my networks.
```
MASQUERADE      169.254.0.0/16,\
                192.168.2.0/24,\
                192.168.10.0/24,\
                192.168.20.0/24,\
                192.168.30.0/24,\
                192.168.40.0/24,\
                192.168.50.0/24     wan

```

In the `zones` file I added:

```
wifi    ipv4
srv     ipv4
bnet    ipv4
guest   ipv4
dmz     ipv4
```

# Blocking everything

The idea of this setup was to remove un-needed access to everything, so I started by removing external access to everything I could think of:

```
# Deny NTP and DNS to the internet, we serve our own and advertise it via DHCP
NTP(REJECT)    loc        net
DNS(REJECT)    loc        net
```

This implicitly left:

* srv, bnet and dmz without any connectivity at all

# Allowing what's needed

As stated in the image, I needed some connection between the VLANs:

* lbalancer -> rproxy tcp on port 80
* sonarr, twitch -> Internet(http, 80 and 443)
* rproxy -> sonarr (as we access sonarr via the lbalancer even internally)

# Issues

I (unsuprisingly!) ran into some issues, even though in theory everything should be OK:

* Certain devices don't give a shit. Chromecast ignores the NTP server assigned by the DHCP server.
* Madsonic (service I use to self host music) requires internet access to start (!!). They are downloading `xsd` files from  both `springframework.org`, `maven.apache.org` and `java.sun.com`. Without these files, Madsonic refuses to start. After this issue I'll look for another music player.
* I am currently having an issue routing from `rproxy` (VLAN 20) to the physical server on it's untagged interface.
  * If I connect from `rproxy`(20) to server(20) then it works fine (via the linux virtual bridge, never reaches the router)
  * Otherwise packets are being dropped, even though the router sees them.

# "Fixes"

## NTP for chromecast:

```
DNAT        wifi    loc:192.168.2.1             udp    123
```

I just map any NTP request coming from `wifi` to my NTP server

## Unable to route

I added IP for the physical server (VLAN 20) in `/etc/hosts` for the `rproxy` container, which makes it "work".

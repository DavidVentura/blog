After adding a fancy router to my setup I decided to monitor my network (now that it is possible). Having already a Grafana+InfluxDB setup for my standard monitoring I decided to (somehow) feed the network data into this setup.

# Compile ipt\_NETFLOW kernel module

To build [ipt-netflow](https://github.com/aabc/ipt-netflow) I needed to install some dependencies first: `dkms iptables-dev pkg-config build-essential git-core`.  
On the espressobin I also needed `linux-headers-next-mvebu64` instead of `linux-headers-$(uname -r)`.

# build / install

```
git clone https://github.com/aabc/ipt-netflow.git
cd ipt-netflow
./configure
make all install
depmod
```
# test it out

As root (change your destination ip/port):

```
modprobe ipt_NETFLOW destination=192.168.2.12:2055
iptables -I FORWARD -j NETFLOW                                                                                                                        
iptables -I INPUT -j NETFLOW                                                                                                                          
iptables -I OUTPUT -j NETFLOW    
```

Start a netflow collector. I adapted a netflow decoder I found [here](http://blog.devicenull.org/2013/09/04/python-netflow-v5-parser.html) with protocol help from [here](https://www.plixer.com/support/netflow-v5/) so I could make it feed my data into InfluxDB. You can find my script [here](https://github.com/DavidVentura/Netflow-to-influx).


# Write some queries in grafana

```
SELECT sum("value") FROM "net_if" WHERE "scidr" = '192.168.2.0/24' AND "dcidr" = '0.0.0.0/0' AND "dport" != '80' AND "dport" != '443' AND "daddr" != '224.0.0.251' AND $timeFilter GROUP BY time(24h), "saddr", "daddr", "dport" fill(none)
```

You end up with something like this:

![](images/lan_wan_usage.png)

# Future
I want to investigate using elasticsearch+kibana as it at least supports IPs as native datatypes, which would allow me to NOT have to decide on the `cidr` myself. Also you can do fancy global graphs with data usage.

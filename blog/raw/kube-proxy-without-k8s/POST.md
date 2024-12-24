---
date: 2024-12-11
title: Kube-proxy without kubernetes
tags: kubernetes, load-balancing
description: Get the best part of kubernetes (services) without kubernetes 
slug: kube-proxy-without-k8s
incomplete: true
---

I've been exploring how to provide high availability for some client-server applications with some unusual constraints:

1. I can install software on the client servers (or make any other necessary adjustments)
2. I can't necessarily modify the client software itself (config is fair game though)
    a. If the client software itself does not support multiple back-ends, then it's not really feasible to adjust it
3. I can't re-arrange the client and server physical locations, they may be spaced to mitigate conjoined failures
4. The traffic is TCP and UDP -- not necessarily HTTP.

-, when the _physical_ location of clients and server is not known in advance.

There's a set of constraints:

1. We need to run few instances of many different clients (100 clients, 2-3 instances each)
2. It's not really feasible to modify the clients
3. The clients are intentionally on geographically separate areas (read: different countries)

And a set of goals:

1. Minimize latency (not in an absolute sense, but avoid egregious extra hops)
2. Simple operation (configuration updates, version upgrades)


Let's look at the options:

## Centralized proxy

It's great when you have good placement -- the proxy does not drastically extend the path between client and server
<img src="assets/proxy-good-placement.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

But in some cases...
<img src="assets/proxy-bad-placement.svg" style="margin: 0px auto; width: 100%; max-width: 40rem" />

Disqualifying, bug also:
- Crash bad
- Upgrade hard

### DNS

DNS solves a large part of the issue, even if the DNS resolver is far away, the latency cost is not paid on every message, rather
only when initiating new connections, and even then, it's guaranteed to happen less frequently than "once per TTL"

<img src="assets/dns.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

Looks pretty good! No data path issues

Downsides:

- DNS records need to change, so TTLs cannot be "large" -- you need to accept "1 TTL" of downtime, so.. 5 minutes?
- Some applications and frameworks are badly behaved, meaning that they resolve the domain _once_ and they cache the results forever, ignoring TTL
- If the DNS server crashes, the data path will be affected once the TTLs expire
    - Fairly easy to mitigate by having multiple DNS servers and round-robin lookups

## Client-side userspace proxy

We can take the proxy concept and move it to the client, taking the placement issue out of the equation

<img src="assets/tcp-proxy.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

If this proxy is a userspace component, that is, a program that listens for connections and pipes the data to selected backends we get a few features for free:

- Can detect when a connection to a backend is interrupted and immediately remove it from the backend options
- Low latency, as there are "no" unnecessary network hops (there are some extra memory copies, but that's negligible in this scenario)

But we also have some drawbacks:

- If the proxy crashes, all connections are disrupted
- Updates / Upgrades are hard -- you can perform a very specific dance and pass open connections to the process that will replace it

## Client-side kernelspace proxy

Working with the above, the data plane was getting mixed with the control plane, which we should try to avoid.

What we can do, is move the "proxying" of the data to kernel space with IPVS.

IPVS (IP Virtual Server) is a Linux feature that allows for [Layer-4]() (so, TCP and UDP) "load balancing"

The way IPVS works is by rewriting destinations on IP packets before they are sent to the network.

how?

There are tables which define a Service (a virtual IP & port) and a set of Destinations (real addresses "backing" the Service)

For example, "Service1" can be defined as:

- Virtual IP: 10.0.0.1
- Port: 1234
- Destinations:
    - Real IP: 1.2.3.4
    - Port: 8888


<img src="assets/ipvs-example.svg" style="margin: 0px auto; width: 100%; max-width: 15rem" />

To manage the IPVS rules, we need a userspace component (could be something smart, or a script that just calls `ipvsadm`) but this component is _specifically_ constrained to the control plane.

The main advantage over the userspace proxy is that there's no "software to upgrade or restart" (well, the kernel, but those upgrades are disruptive anyway)

However, we lost a very nice property from the userspace proxy: being able to quickly detect closed connections and act accordingly (eg: by quarantining them for a little bit)


We can extend the userspace component, with the capability to detect closed connections; how?

✨ eBPF ✨

eBPF is a mechanism in the Linux kernel that allows us to run [verified](https://docs.ebpf.io/linux/concepts/verifier/) programs _within_ the kernel, hooking into events and sending data with userspace applications through maps.

We would like to end up in the magical land where this is possible:

```rust
async fn handle_events(mut events: EventStream) {
    while let Some(event) = events.next().await {
        match event.interpret() {
            ConnectionState::Failed(backend) => {
                mark_backend_suspect(backend);
            },
            ConnectionState::Established(backend) => {
                record_successful_connection(backend);
            },
        }
    }
}
```

So.. let's build it!

## Researching the data path

We want to get notified when there's a state change on a (specific) TCP connection, and would you look at that, there's a [inet\_sock\_set\_state](TODO) function that we can start with.

These examples are summarized, the repo is [here](https://github.com/DavidVentura/ipvs-tcp-from-scratch).

```rust
#![no_std]
use core::net::Ipv4Addr;

pub struct TcpSocketEvent {
    pub oldstate: TcpState,
    pub newstate: TcpState,
    pub src: Ipv4Addr,
    pub sport: u16,
    pub dst: Ipv4Addr,
    pub dport: u16,
}

#[tracepoint]
pub fn inet_sock_set_state(ctx: TracePointContext) -> i64 {
    let evt_ptr = ctx.as_ptr() as *const trace_event_raw_inet_sock_set_state;
    let evt = unsafe { evt_ptr.as_ref().ok_or(1i64)? };
    if evt.protocol != IPPROTO_TCP {
        return 0;
    }
    let ev: TcpSocketEvent = make_ev_from_raw(evt);
    if let Some(ev) = make_ev_from_raw(&ctx, evt) {
        let os_name: &'static str = ev.oldstate.into();
        let ns_name: &'static str = ev.newstate.into();
        info!(
            &ctx,
            "TCP connection {}:{}->{}:{} changed state {}->{}",
            ev.src, ev.sport, ev.dst, ev.dport, os_name, ns_name
        );
    }
    Ok(0)
}
```

If we run this program and perform a `curl`, we get a very nice output:
```bash
$ tracer & curl -s example.com
TCP connection 192.168.2.144:0    ->93.184.215.14:80 changed state Close      -> SynSent
TCP connection 192.168.2.144:47256->93.184.215.14:80 changed state SynSent    -> Established
TCP connection 192.168.2.144:47256->93.184.215.14:80 changed state Established-> FinWait1
TCP connection 192.168.2.144:47256->93.184.215.14:80 changed state FinWait1   -> FinWait2
TCP connection 192.168.2.144:47256->93.184.215.14:80 changed state FinWait2   -> Close

```

So far so good! Now let's try tracing an IPVS connection

```bash
$ # Create a service for 1.2.3.4:80
$ ipvsadm -A  --tcp-service 1.2.3.4:80
$ # Create a destination pointing to 'example.com' (IP from previous point)
$ ipvsadm -a --tcp-service 1.2.3.4:80 -r 93.184.215.14 -m
$ tracer & curl -s 1.2.3.4:80
TCP connection 192.168.2.144:0    ->1.2.3.4:80 changed state Close      -> SynSent
TCP connection 192.168.2.144:39040->1.2.3.4:80 changed state SynSent    -> Established
TCP connection 192.168.2.144:39040->1.2.3.4:80 changed state Established-> FinWait1
TCP connection 192.168.2.144:39040->1.2.3.4:80 changed state FinWait1   -> FinWait2
TCP connection 192.168.2.144:39040->1.2.3.4:80 changed state FinWait2   -> Close

```

Let's now add a "bad" backend to the service (there's nothing listening on that address):
```bash
$ ipvsadm -a --tcp-service 1.2.3.4:80 -r 192.168.2.100 -m
```

When we run `curl` again, we see a failed connection.. but, to which backend?
```text
TCP connection 192.168.2.144:0    ->1.2.3.4:80 changed state Close   -> SynSent           
TCP connection 192.168.2.144:57478->1.2.3.4:80 changed state SynSent -> Close
```

We somehow need to enrich the TCP state transition data with IPVS data, so let's look at IPVS events:

[ip\_vs\_conn\_new]() sounds _very_ promising, though there is no tracepoint for it, so we will need to use a [kprobe](), which is not ideal.

In `ip_vs_conn_new`, we get an [ip\_vs\_conn\_param](), a destination address ([nf\_inet\_addr]()) and a destination port

Let's also hook into it and see what we get

```rust
pub struct IpvsParam {
    saddr: Ipv4Addr, // TCP source address
    sport: u16,      // TCP source port
    vaddr: Ipv4Addr, // TCP dest address (virtual)
    vport: u16,      // TCP dest port (virtual)
    daddr: Ipv4Addr, // TCP dest address (real)
    dport: u16,      // TCP dest port (real)
}

#[kprobe]
pub fn ip_vs_conn_new(ctx: ProbeContext) -> u32 {
    let conn_ptr: *const ip_vs_conn_param = ctx.arg(0).ok_or(0u32)?;
    let conn = unsafe { helpers::bpf_probe_read_kernel(&(*conn_ptr)).map_err(|x| 1u32)? };
    let param: IpvsParam = make_ipvs_param_from_raw(conn);
    info!(
        ctx,
        "{}:{} -> virtual={}:{} real={}:{}",
        param.saddr, param.sport,
        param.vaddr, param.vport,
        param.daddr, param.dport
    );
}
```

If we trace a connection again, we get lucky and hit a good backend:
```text
TCP  connection 192.168.2.144:0->1.2.3.4:80 changed state Close->SynSent

IPVS connection 192.168.2.144:39634 -> virtual=1.2.3.4:80 real=93.184.215.14:80

TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state SynSent->Established
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state Established->FinWait1
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state FinWait1->FinWait2
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state FinWait2->Close
```
But after a little bit, we try again and we hit the bad backend:
```text
TCP  connection 192.168.2.144:0->1.2.3.4:80 changed state Close->SynSent

IPVS connection 192.168.2.144:49512 -> virtual=1.2.3.4:80 real=192.168.2.100:80

TCP  connection 192.168.2.144:49512->1.2.3.4:80 changed state SynSent->Close
```

This is all the information we need, now we just need to put it together:

As this event happens _before_ the TCP connection is started, we can save this data, to later look it up during TCP events;

during the socket state transition we have a 5-tuple that identifies the connection:

```
(proto, source addr, source port, dest addr, dest port)
```

and during the IPVS events we have that, _plus_ the real address and port

We will need to split the IpvsParam into two parts, which we can use in a hashmap, first, a key:
```rust
struct TcpKey {
    saddr: IpAddr, // TCP source address
    sport: u16,    // TCP source port
    vaddr: IpAddr, // TCP dest address (virtual)
    vport: u16,    // TCP dest port  (virtual)
}
```

and a value:
```rust
pub struct IpvsDest {
    pub daddr: IpAddr,
    pub dport: u16,
}
```

```rust
#[map]
static IPVS_TCP_MAP: HashMap<TcpKey, IpvsDest> = HashMap::with_max_entries(1024, 0);
```

```
Error: the BPF_PROG_LOAD syscall failed. Verifier output: last insn is not an exit or jmp
verification time 9 usec
processed 0 insns (limit 1000000) max_states_per_insn 0 total_states 0 peak_states 0 mark_read 0
```
wat
turns out if you
```
IPVS_TCP_MAP.insert(key, value, 0).unwrap()
```
can be fixed with
```
IPVS_TCP_MAP.insert(key, value, 0).is_ok()
```

```
getting key 192.168.0.185:0 1.2.3.4:80 for state Close->SynSent
Ignoring TCP conn not going to IPVS
IPVS mapping inserted 192.168.0.185:55264 1.2.3.4:80
getting key 192.168.0.185:55264 1.2.3.4:80 for state SynSent->Established
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state SynSent->Established
getting key 192.168.0.185:55264 1.2.3.4:80 for state Established->FinWait1
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state Established->FinWait1
getting key 192.168.0.185:55264 1.2.3.4:80 for state FinWait1->FinWait2
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state FinWait1->FinWait2
getting key 192.168.0.185:55264 1.2.3.4:80 for state FinWait2->Close
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state FinWait2->Close
```


now, we have access to this hashmap during the TCP state transitions, and it now looks a lot more promising

BUT! you can see that the first state transition does not get the IPVS data, there are two important aspects:
- the `Close->SynSent` event, _for some reason_, is triggered BEFORE the source port assignment; why?? it's CLEARLY not sent a SYN packet with source port =0.
- the state transition is triggered BEFORE the backend selection, which again, makes no sense, how do you send a SYN packet when you don't know the real address??

there's this comment that states this is intended

```c
/* Socket identity is still unknown (sport may be zero).
 * However we set state to SYN-SENT and not releasing socket
 * lock select source port, enter ourselves into the hash tables and
 * complete initialization after this.
 */
inet_sock_set_state(sk, TCP_SYN_SENT);
```

I'd guess that it's to pprevent race conditions which don't acquire the lock?
If state is SynSent and port is 0, it'd mean the socket has no port assigned yet, but if state
is Closed and port is 0, what does that mean? though, i'm not sure it's relevant

```c
// See:
// https://github.com/torvalds/linux/blob/v6.11/net/ipv4/tcp_ipv4.c#L294
// tcp_connect is called here:
// https://github.com/torvalds/linux/blob/v6.11/net/ipv4/tcp_ipv4.c#L337
// critically, after `inet_hash_connect`, which assigns the source port.
```

by reading `tcp_v4_connect` we can hook into `tcp_connect` which is called with the lock held (TODO) and
_after_ the source port is assigned.

```rust
#[kprobe]
pub fn tcp_connect(ctx: ProbeContext) -> u32 {
    let conn_ptr: *const sock = ctx.arg(0).ok_or(0u32)?;

    let sk_comm =
        unsafe { helpers::bpf_probe_read_kernel(&((*conn_ptr).__sk_common)).map_err(|x| 999u32)? };
    // By definition, `tcp_connect` is called with SynSent state
    // This `if` will never trigger -- it is here only to make the
    // expected precondition explicit
    if sk_comm.skc_state != TcpState::SynSent as u8 {
        return Err(888);
    }
    let key = tcp_key_from_sk_comm(sk_comm);

    info!(
        ctx,
        "after hash; getting key {}:{} {}:{} for state CLOSE->SYNSENT",
        key.saddr,
        key.sport,
        key.vaddr,
        key.vport,
    );
    0
}
```
and we get

```text
getting key 192.168.0.185:0 1.2.3.4:80 for state Close->SynSent
Ignoring TCP conn not going to IPVS
after hash; getting key 192.168.0.185:37862 1.2.3.4:20480 for state CLOSE->SYNSENT
IPVS mapping inserted 192.168.0.185:37862 1.2.3.4:80
getting key 192.168.0.185:37862 1.2.3.4:80 for state SynSent->Close
TCP connection 192.168.0.185:37862->1.2.3.4:80 (real 192.168.2.100:80) changed state SynSent->Close
```

so, we now can get the `Close->SynSent` event with a source port, but it still happens _before_ the backend selection

we can only use this event for timing information on further events


## NEXT -> send events to userspace
## THEN -> identify local close and remote close via rcv_reset
## THEN -> find timeout before they happen with retrans
--- 
crux of the ebpf impl, svc being Option is because the trace of `inet_sock_set_state` happens _before_ a source port is assigned!
this _sucks_.. but.. we can cheat a little bit, by tracing _any function_ that receives a useful context, while the tcp lock is held,
we can get access to the late-initialized sourceport; in this case, `tcp_connect` is a perfect function for that.


So, in summary, if we trace the IPVS connection establishment, we can enrich further TCP socket transitions with the IPVS Destination (instead of just Service address)

And, if we can push TCP state changes with Service+Destinations to userspace, we can decide what to do.

Something like this
```rust
info!("Waiting for Ctrl-C...");
let mut watcher = ConnectionWatcher::new()?;
let mut rx = watcher.get_events().await?;
while let Some(i) = rx.recv().await {
    println!("{:?} = {:?}", i, i.interpret());
}
signal::ctrl_c().await?;
info!("Exiting...");
```


TODO: client side vs server side interrupt, by tcp_receive_reset

which has all the upsides of the userspace connection proxy, and none of the downsides (beyond any sanity lost while trying to coerce `aya` + the eBPF verifier into letting me access valid pointers)

### On `kprobe`s and testing
<small>
Aside: Using a `kprobe` is not ideal, because tracepoints are stable interfaces and maintained by the kernel developers, while kprobes are "probing points" which we can use, but there are no stability guarantees.
No stability guarantees across kernel versions means that we get to add integration testing for each supported version

TODO maybe use this as a footnote for firetest.
</small>


---

This precludes having a static set of proxies, as the location may be a problem

Client [France] -> Proxy [Lithuania] -> Server [France] 

would be a problem

we want to minimize latency, hops, and single points of failure.

The solution I "came up with" is to mimic the `Service` concept in Kubernetes, which boils down to: have dedicated "virtual" IPs, which point to the "correct" backend for every client

To make networking simple, these IPs are never actually used as destinations over the wire, instead, the packets are rewritten before leaving the "Client" machine.

This is done with IPVS (explanation), which can rewrite destination addresses before they leave the wire

```
ipvsadm something add
```

## Compared to alternatives

Centralized proxy:
* :X:



## Downsides
- Every **Client** needs to have the IPVS daemon

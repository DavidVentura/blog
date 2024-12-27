---
date: 2024-12-11
title: Implementing a client side IPVS-based load balancer
tags: load-balancing
description: Get the best part of kubernetes (services) without kubernetes 
slug: ipvs-lb
incomplete: true
---

I've been exploring how to provide high availability for some client-server applications with some unusual constraints:

1. I can install software on the client servers (or make any other system adjustments)
2. I can't modify the client software itself (config is fair game though)
3. I can't re-arrange the client and server physical locations, they may be spaced to mitigate conjoined failures
4. The traffic is TCP and UDP -- not necessarily HTTP.

And a set of goals:

1. Minimize latency (not in an absolute sense, but avoid egregious extra hops)
2. Simple operation (configuration updates, version upgrades)

Let's look at the options:

## Centralized proxy

A centralized proxy receives connections from all the clients and distributes them among the servers;
It's a great solution when you have control of the placement, meaning that the proxy does not drastically
extend the path between client and server:
<img src="assets/proxy-good-placement.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

But in some cases, the distributed placement of the clients and servers ends up with unnecessarily long paths:


<img src="assets/proxy-bad-placement.svg" style="margin: 0px auto; width: 100%; max-width: 40rem" />

The placement constraint alone would disqualify this solution, but on top of that, dealing with proxy crashes (software or server) 
would require more proxies, and balancing between those.

### DNS

Using DNS for availability solves the previous issue; the data path is now as short as possible, and the cost of record lookups
is amortized over all the connections that are established on each TTL period.

<img src="assets/dns.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

Looks pretty good! No data path issues

There are some downsides still though:

- TTLs cannot be "large" -- you need to accept "1 TTL" of downtime
- Some applications and frameworks misbehave and ignore TTLs, meaning that they resolve the domain _once_ and they cache the results forever
- If the DNS server crashes, the data path will be affected once the TTLs expire
    - Fairly easy to mitigate by having multiple DNS servers and round-robin lookups

## Client-side userspace proxy

all clients connect to `localhost:...` and the data is forwarded to the respective servers. server resolution is out of band.

If we were to install a proxy on every client, we would get rid of the placement issues from the centralized proxies and the "misbehaving" applications issues
from the DNS solution 

We can take the proxy concept and move it to the client, taking the placement issue out of the equation

<img src="assets/tcp-proxy.svg" style="margin: 0px auto; width: 100%; max-width: 35rem" />

If this proxy is a userspace component, that is, a program that listens for connections and pipes the data to selected backends we get a few features for free:

- Can detect when a connection to a backend is interrupted and immediately remove it from the backend options
- Low latency, as there are "no" unnecessary network hops (there are some extra memory copies, but that's negligible in this scenario)

But we also have some drawbacks:

- If the proxy crashes, all connections are disrupted
- Updates / Upgrades are hard[^upgrade]

[^upgrade]: Although you _can_ perform a very specific dance and pass open connections to the child process that will replace the running proxy

Can we do better?

## Client-side kernelspace proxy

On the previous example, the proxy software _could_ have issues which would impact the data plane, and we should avoid that if possible.

What we can do instead, is move the "proxying" of the data to kernelspace, by using [IPVS (IP Virtual Server)](), which is a Linux feature
that allows for [Layer-4]() (so, TCP and UDP) "load balancing"

The way IPVS works is by rewriting destinations on IP packets before they are sent to the network.

how?

We can define a `Service` (a virtual IP & port) as a set of `Destination` (real addresses "backing" the Service), when traffic would flow to the `Service`,
instead, it is re-written to be sent to one of the `Destination`s

For example, "Service1" can be defined as:

- Virtual IP: 10.0.0.1
- Port: 1234
- Destinations:
    - Real IP: 1.2.3.4; Port: 8888
    - Real IP: 4.4.4.4; Port: 8888


The IPVS rule definitions are kernel datastructures, these can be updated via [netlink](); to do so, we need a userspace component
(eg: `ipvsadm`) but this component is _specifically_ constrained to the control plane.

The main advantage over the userspace proxy is that there's no "software to upgrade or restart" (well, the kernel, but those upgrades are disruptive anyway)

However, we lost a very nice property from the userspace proxy: being able to quickly detect closed connections and act accordingly (eg: by quarantining the respective destination for some time)

Can we extend the userspace component with the capability to detect closed connections?

Yes, with the solution to all problems: ✨ eBPF ✨.

eBPF is a mechanism in the Linux kernel that allows us to run [verified](https://docs.ebpf.io/linux/concepts/verifier/) programs _within_ the kernel, hooking into events and sending data with userspace applications.

We would like to end up in the magical land where this is possible:

```rust
async fn handle_events(mut events: EventStream) {
    while let Some(event) = events.next().await {
        match event.interpret() {
            ConnectionState::Failed(backend) => {
                quarantine_backend(backend);
            },
            ConnectionState::Established(backend) => {
                record_successful_connection(backend);
            },
        }
    }
}
```

So.. let's build it!

For this project, we'll be using [Aya](), which is a library that simplifies writing eBPF code in Rust.

<small> All the examples in this post are summarized, the repo is [here](https://github.com/DavidVentura/ipvs-tcp-from-scratch).</small>

## Researching the data path

We want to get notified when there's a state change on TCP connections, luckily there's a `inet_sock_set_state`
[tracepoint](https://github.com/torvalds/linux/blob/v6.12/include/trace/events/sock.h#L141)
that we can use for exactly this purpose:

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

on the userspace side, we need to hook this `inet_sock_set_state` function to the kernel tracepoint,
which we identify by `category` and `name`.

All tracepoints can be listed at `/sys/kernel/debug/tracing/events`.

```rust
let program: &mut TracePoint = ebpf
    .program_mut("ipvs_tcp_from_scratch")
    .unwrap()
    .try_into()?;
program.load()?;
program.attach("sock", "inet_sock_set_state")?;
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
Huh.. we see the virtual IP, not the real ip here, I guess that makes sense -- the 
destination IP will be rewritten without the TCP layer being aware.

Let's now test with a "bad" backend on the service (there's nothing listening on that address):
```bash
$ ipvsadm -a --tcp-service 1.2.3.4:80 -r 192.168.2.100 -m
TCP connection 192.168.2.144:0    ->1.2.3.4:80 changed state Close   -> SynSent           
TCP connection 192.168.2.144:57478->1.2.3.4:80 changed state SynSent -> Close
```
We see the failed connection.. but, to which backend?

We somehow need to enrich the TCP state transition data with IPVS data, so let's look at IPVS events:

[ip\_vs\_conn\_new](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/ipvs/ip_vs_conn.c#L941) sounds
_very_ promising, though there is no tracepoint for it, so we will need to use a [kprobe](https://docs.kernel.org/trace/kprobes.html), which is not ideal.

In `ip_vs_conn_new`, we get an [ip\_vs\_conn\_param](https://github.com/torvalds/linux/blob/v6.12/include/net/ip_vs.h#L548),
 a destination address ([nf\_inet\_addr](https://github.com/torvalds/linux/blob/v6.12/include/uapi/linux/netfilter.h#L72)) and a destination port

Let's hook into it and see what we get

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

If we trace a connection again, we may get lucky and hit the good backend:
```text
TCP  connection 192.168.2.144:0->1.2.3.4:80 changed state Close->SynSent

IPVS connection 192.168.2.144:39634 -> virtual=1.2.3.4:80 real=93.184.215.14:80

TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state SynSent->Established
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state Established->FinWait1
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state FinWait1->FinWait2
TCP  connection 192.168.2.144:39634->1.2.3.4:80 changed state FinWait2->Close
```

Or we may be a little less lucky and we hit the bad backend:
```text
TCP  connection 192.168.2.144:0->1.2.3.4:80 changed state Close->SynSent

IPVS connection 192.168.2.144:49512 -> virtual=1.2.3.4:80 real=192.168.2.100:80

TCP  connection 192.168.2.144:49512->1.2.3.4:80 changed state SynSent->Close
```

This is all the information we need for basic analysis, now we just need to put it together.

## Putting event data together

We do not have the same data available to us in both events (`ip_vs_conn_new` and `inet_sock_set_state`); 
during the socket state transition we have a 5-tuple that uniquely identifies a connection:

```text
(proto, source addr, source port, dest addr, dest port)
```

and during the IPVS events we have that, _plus_ the real address and port (the chosen IPVS destination).

Given this, we can create a new type to identify a TCP connection:

```rust
struct TcpKey {
    saddr: IpAddr, // TCP source address
    sport: u16,    // TCP source port
    vaddr: IpAddr, // TCP dest address (virtual)
    vport: u16,    // TCP dest port  (virtual)
}
```

and we can update `TcpSocketEvent` to use the `TcpKey`:
```rust
pub struct TcpSocketEvent {
    pub oldstate: TcpState,
    pub newstate: TcpState,
    pub key: TcpKey,
}
```

Previously, `IpvsParam` was defined before as the "expanded" TCP Key along with the real destination from IPVS.

We can now define the destination tuple as its own type:
```rust
pub struct IpvsDest {
    pub daddr: IpAddr,
    pub dport: u16,
}
```

and delete `IpvsParam`, which can now be represented as a pair of `(TcpKey, IpvsDest)`.

During both events (`inet_sock_set_state` and `ip_vs_conn_new`) we have access to a key which uniquely
identifies the connection, FIXME this is duplicate; the way to bridge this is to use a `HashMap` --
insert data during `ip_vs_conn_new` and look it up during `inet_sock_set_state`

First, we declare a special [HashMap](https://docs.rs/aya/latest/aya/maps/hash_map/struct.HashMap.html)
 (which could be shared with userspace, but we don't need that property).

```rust
#[map]
static IPVS_TCP_MAP: HashMap<TcpKey, IpvsDest> = HashMap::with_max_entries(1024, 0);
```


To keep state between the `ip_vs_conn_new` call and the followup `inet_sock_set_state` calls, we can 
insert the data during `ip_vs_conn_new`:
```rust
IPVS_TCP_MAP.insert(key, value, 0).unwrap()
```

and read it back during `inet_sock_set_state`:
```rust
let key: TcpKey = make_key_from_raw(&ctx, evt);
let ipvs_data: Option<IpvsDest> = IPVS_TCP_MAP.get(&key);
```

<div class="aside">
<p>
or.. can we? The verifier was <i>not happy</i> about this change:

```text
Error: the BPF_PROG_LOAD syscall failed. Verifier output: last insn is not an exit or jmp
verification time 9 usec
processed 0 insns (limit 1000000) max_states_per_insn 0 total_states 0 peak_states 0 mark_read 0
```

turns out that calling <code>unwrap()</code> is not fine, even though it's never <i>actually</i> called.

A simple change of

```diff
-IPVS_TCP_MAP.insert(key, value, 0).unwrap()
+IPVS_TCP_MAP.insert(key, value, 0).is_ok()
```

fixes the issue.

</p>
</div>


If we observe the events now, we can see the real IP after the connection is established
```bash
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real unknown)          changed state Close->SynSent
IPVS mapping inserted 192.168.0.185:55264 1.2.3.4:80
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state SynSent->Established
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state Established->FinWait1
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state FinWait1->FinWait2
TCP connection 192.168.0.185:55264->1.2.3.4:80 (real 93.184.215.14:80) changed state FinWait2->Close
```

This information starts looking useful

## Passing data to userspace

so far we've been printing events to stdout, but that's not too useful, we want to apply some logic and take action based on these events, so we need to send them to userspace

`aya` makes this extremely easy, by providing a [PerfEventArray](), we can pass data to userspace through a per-cpu ring buffer

```rust
#[map]
static mut TCP_EVENTS: PerfEventArray<TcpSocketEvent> = PerfEventArray::new(0);

fn push_tcp_event<C: EbpfContext>(ctx: &C, evt: &TcpSocketEvent) {
    unsafe {
        #[allow(static_mut_refs)]
        TCP_EVENTS.output(ctx, evt, 0);
    }
}
```

In `inet_sock_set_state` and `tcp_connect` we were logging the TCP events, we now construct a `TcpSocketEvent` instance and push it through the perf buffer
```rust
let ev = TcpSocketEvent {
  // ...
};
push_tcp_event(ctx, &ev);
```

in `tcp_connect` we have a bit of a special case -- we don't receive the old and new states, but by definition they **must** be `Close` and `SynSent` respectively.

After setting this up, along with an async poller for the buffer (see [repo]() for details), we can
Log the results _in userspace_:

```rust
let mut rx = watch_tcp_events(events).await.unwrap();
for ev in rx.recv() {
    println!("got ev {ev:?}");
}
```

```text
got ev TcpSocketEvent { oldstate: Close,       newstate: SynSent,     src: 192.168.0.185, sport:     0, dst: 1.2.3.4, dport: 80 }
got ev TcpSocketEvent { oldstate: SynSent,     newstate: Established, src: 192.168.0.185, sport: 46780, dst: 1.2.3.4, dport: 80 }
got ev TcpSocketEvent { oldstate: Established, newstate: FinWait1,    src: 192.168.0.185, sport: 46780, dst: 1.2.3.4, dport: 80 }
got ev TcpSocketEvent { oldstate: FinWait1,    newstate: FinWait2,    src: 192.168.0.185, sport: 46780, dst: 1.2.3.4, dport: 80 }
got ev TcpSocketEvent { oldstate: FinWait2,    newstate: Close,       src: 192.168.0.185, sport: 46780, dst: 1.2.3.4, dport: 80 }
```

which is great, but we didn't yet define the IPVS side of the data on `TcpSocketEvent`

TODO join these two sections

## THEN -> pass also the Option<Service>

If we extend `TcpSocketEvent` with an `Option<IpvsDest>` field, we can populate it with the hashmap values on `inet_sock_set_state`, something like this:

```rust
if let Some(key) = make_key_from_raw(&ctx, evt) {
    let v = unsafe { IPVS_TCP_MAP.get(&key) }.copied();
    let v = v.unwrap();
    let ev = TcpSocketEvent {
        // ..
        ipvs_dest: Some(v),
    };
    push_tcp_event(&ctx, &ev);
}
```

```rust
TcpSocketEvent { oldstate: Close,       newstate: SynSent,     src: 192.168.0.185, sport:     0, dst: 1.2.3.4, dport: 80, ipvs_dest: None }
TcpSocketEvent { oldstate: SynSent,     newstate: Established, src: 192.168.0.185, sport: 49622, dst: 1.2.3.4, dport: 80, ipvs_dest: Some(IpvsDest { daddr: 93.184.215.14, dport: 80 }) }
TcpSocketEvent { oldstate: Established, newstate: FinWait1,    src: 192.168.0.185, sport: 49622, dst: 1.2.3.4, dport: 80, ipvs_dest: Some(IpvsDest { daddr: 93.184.215.14, dport: 80 }) }
TcpSocketEvent { oldstate: FinWait1,    newstate: FinWait2,    src: 192.168.0.185, sport: 49622, dst: 1.2.3.4, dport: 80, ipvs_dest: Some(IpvsDest { daddr: 93.184.215.14, dport: 80 }) }
TcpSocketEvent { oldstate: FinWait2,    newstate: Close,       src: 192.168.0.185, sport: 49622, dst: 1.2.3.4, dport: 80, ipvs_dest: Some(IpvsDest { daddr: 93.184.215.14, dport: 80 }) }
```

## Enrich the 'open' event

BUT! you can see that the first state transition (Close&rarr;SynSent) does not get the IPVS data, there are two important aspects:
- This event, for some reason, is triggered _before_ the source port assignment; I don't understand why &mdash; the kernel has _not_ sent a `SYN` packet with source port 0.
- This event is also is triggered _before_ the backend selection, which makes sense, the backend will only be chosen once a connection establishment is attempted

[In the sources](https://github.com/torvalds/linux/blob/v6.12/net/ipv4/tcp_ipv4.c#L297), there's a comment in `tcp_v4_connect` which states this behavior is intended:
```c
/* Socket identity is still unknown (sport may be zero).
 * However we set state to SYN-SENT and not releasing socket
 * lock select source port, enter ourselves into the hash tables and
 * complete initialization after this.
 */
inet_sock_set_state(sk, TCP_SYN_SENT);
```

by reading `tcp_v4_connect`, we can [see](https://github.com/torvalds/linux/blob/v6.12/net/ipv4/tcp_ipv4.c#L341) that the `tcp_connect` function is called:

- with the lock still held
- _after_ the call to `inet_hash_connect` (which assigns the source port, if necessary)
- with the `struct sock*` as argument

which makes it a _perfect_ target for introspection! Well, almost, we still need to use `kprobe` as there is no official tracepoint.


Tracing it is similar to what we've been doing so far
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
    let ev = TcpSocketEvent {
        oldstate: TcpState::Close,
        newstate: TcpState::SynSent,
        src: key.saddr,
        sport: key.sport,
        dst: key.vaddr,
        dport: key.vport,
        ipvs_dest: None,
    };
    push_tcp_event(ctx, &ev);
    Ok(0)
}
```
and we get

```text
got ev TcpSocketEvent {
    oldstate: Close,
    newstate: SynSent,
    src: 192.168.2.144,
    sport: 43920,
    dst: 1.2.3.4,
    dport: 80,
    ipvs_dest: None
}
```

with a non-zero source-port! As nice as this is, the `Close->SynSent` transition still happens _before_ the IPVS backend assignment, so we can only use this event for timing information

## Detecting timeouts before they happen
Talking about timing information..

At the beginning, we configured the IPVS service with two addresses, one of which always drops the packets, simulating an unresponsive server.

If we try to connect and trace the events, this is what we get:

FIXME not 3 seconds but 135

```rust
23:25:51 TcpSocketEvent { oldstate: Close,   newstate: SynSent, /* ... */ }
23:25:54 TcpSocketEvent { oldstate: SynSent, newstate: Close,
                          /* ... */
                          ipvs_dest: Some(IpvsDest { daddr: 192.168.2.100, dport: 80 }) }
```

There was no data transmitted for 3 seconds, after which, `curl` decided to close the connection:
```bash
$ time curl 1.2.3.4
curl: (7) Failed to connect to 1.2.3.4 port 80 after 3098 ms: Couldn't connect to server
```

We could track at which time the connection opened and whether there were no state transitions before closing, inferring packets being dropped and marking the backend as unhealthy.

Or!

We could actually track the packet retransmits and mark the backend as unhealthy _before the timeout_, as a lot of software will just hang forever.

The implementation closely follows the previous ones,
```rust
#[tracepoint]
pub fn tcp_retransmit_skb(ctx: TracePointContext) -> Result<i64> {
    let evt_ptr = ctx.as_ptr() as *const trace_event_raw_tcp_event_sk_skb;
    let evt = unsafe { evt_ptr.as_ref().ok_or(1i64)? };
    let state: TcpState = evt.state.into();
    // We only care about connection opening, to detect timeouts
    if let TcpState::SynSent = state {
        let key = tcp_key_from_sk_skb(evt);
        let v = unsafe { IPVS_TCP_MAP.get(&key) }.copied();
        if v.is_none() {
            // Not IPVS related, we don't care
            return Ok(0);
        }
        let evt = TcpSocketEvent {
            oldstate: TcpState::SynSent,
            newstate: TcpState::SynSent,
            // ...
        };
        push_tcp_event(ctx, &evt);
    }
    Ok(0)
    }
}
```

There is only one interesting thing here, we do not care about the retransmits for any connection which is not in `SynSent` state, those connections are already established -- maybe we _could_ care, in a way, to detect hosts going offline, but it's not necessary for now.


```bash
$ curl 1.2.3.4
00:26:11 TcpSocketEvent { oldstate: Close,   newstate: SynSent, src: 192.168.2.144, sport: 60780, dst: 1.2.3.4, dport: 80, ipvs_dest: None }
00:26:12 TcpSocketEvent { oldstate: SynSent, newstate: SynSent, src: 192.168.2.144, sport: 60780, dst: 1.2.3.4, dport: 80, ipvs_dest: None }
...
00:27:19 TcpSocketEvent { oldstate: SynSent, newstate: SynSent, src: 192.168.2.144, sport: 60780, dst: 1.2.3.4, dport: 80, ipvs_dest: None }
00:28:27 TcpSocketEvent { oldstate: SynSent, newstate: Close,   src: 192.168.2.144, sport: 60780, dst: 1.2.3.4, dport: 80, ipvs_dest: Some(IpvsDest { daddr: 192.168.2.100, dport: 80 }) }

curl: (28) Failed to connect to 1.2.3.4 port 80 after 135807 ms: Couldn't connect to server
```

## But, who closed the connection?

As the last item, we want to find out which side closes the connection -- if the _client_ closes the connection, we do not want to mark the backend as unhealthy!

TODO: `tcp_rcv_reset`

## On `kprobe`s and testing
<small>
Aside: Using a `kprobe` is not ideal, because tracepoints are stable interfaces and maintained by the kernel developers, while kprobes are "probing points" which we can use, but there are no stability guarantees.
No stability guarantees across kernel versions means that we get to add integration testing for each supported version

TODO maybe use this as a footnote for firetest.
</small>

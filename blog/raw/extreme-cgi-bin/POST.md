---
title: Extreme CGI Bin
date: 2023-02-08
tags: shitpost, linux, firecracker
description: ??
incomplete: yes
---

## Introducing Extreme CGI bin: peak web development
Once upon a time, we had [CGI-Bin](https://en.wikipedia.org/wiki/Common_Gateway_Interface) as means of interacting with incoming requests: when a request came in, the HTTP server started a new process to deal with it.

Each process only lived as long as the request, which meant no persistent state, and no bugs from stale resources or memory leaks.

In this regard modern stacks _suck_ -- they run for longer than the requests and even have persistent state!

What if we could change that?

Introducing *Extreme CGI Bin*: Say goodbye to the tyranny of persistent state!

16.925ms

```
0.000000 Linux version 6.7.3 #148 Tue Feb  6 16:51:37 UTC 2024
0.000964 [Firmware Bug]: TSC doesn't count with P0 frequency!
0.006431 Hello!
```
With *Extreme CGI Bin* you can boot into your application _with a network stack_ in {^6 milliseconds|on my laptop, with 1 core, with 128MB memory} or your money back!

-> ARP
-> Connection: close; browsers reusing tcpconn otherwise

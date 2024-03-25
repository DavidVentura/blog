---
title: Running a cross-architecture Nomad cluster
date: 2023-11-12
tags: nomad, aarch64, riscv, cluster, homelab, short
description: 
slug: cross-arch-nomad
---

I wanted to play around with some projects on RISC-V, so I got a [VisionFive 2](https://www.starfivetech.com/en/site/boards) and tried to add it to my Nomad mini cluster. Surprisingly, _nothing_ worked on this experimental platform!

First, Nomad does not provide builds on RISC-V, and it does not build, as it has a transitive dependency on `boltdb`, which itself does not build for RISC-V.

When building Nomad, we need to disable a subset of `boltdb`'s features, can do so by using Elara's fork

```
replace github.com/hashicorp/raft-boltdb/v2 => github.com/Elara6331/raft-boltdb/v2 v2.0.0-20230729002801-1a3bff1d87a7
```

And then we can build with

```bash
make \
	GOOS=linux \
	GOARCH=riscv64 \
	CC=/usr/bin/riscv64-linux-gnu-gcc \
	CXX=/usr/bin/riscv64-linux-gnu-c++ \
	AR=/usr/bin/riscv64-linux-gnu-gcc-ar \
	dev
```

Though, when running `nomad`, I kept having issues with the `raw_exec` driver:

```hcl
job "unamer" {
  type = "batch"

  constraint {
    attribute = "${attr.cpu.arch}"
    value     = "riscv64"
  }
  task "uname-task" {
    driver = "raw_exec"
    config {
      command = "/bin/uname"
      args = ["-a"]
    }
  }
}
```

As it was complaining about being unable to manage cpu slices via cgroups

```
2023-11-12T14:35:14.194Z [INFO]  client.alloc_runner.task_runner: Task event: alloc_id=4744f0ea-7616-ab3a-a420-8e25056e3861 task=envtask type="Setup Failure" msg="failed to setup alloc: pre-run hook \"cpuparts_hook\" failed: open /sys/fs/cgroup/nomad.slice/share.slice/cpuset.cpus: no such file or directory" failed=true
2023-11-12T14:35:14.194Z [ERROR] client.alloc_runner: prerun failed: alloc_id=4744f0ea-7616-ab3a-a420-8e25056e3861 error="pre-run hook \"cpuparts_hook\" failed: open /sys/fs/cgroup/nomad.slice/share.slice/cpuset.cpus: no such file or directory"
```

Comparing to other, better behaving servers, I found that the `/sys/fs/cgroup/controllers` file did not contain the `cpuset` controller.

```
user@starfive:~$ cat /sys/fs/cgroup/cgroup.subtree_control 
cpu
```


Turns out that the default kernel config for the current 5.15 (ew) kernel does not have `CONFIG_CPUSET` enabled, which is what enables the `cpuset` controller. I've sent a [PR](https://github.com/starfive-tech/linux/pull/125) to starfive to update these defaults, but it's not been merged.

I've also sent a [PR](https://github.com/hashicorp/nomad/pull/19176) to Nomad to disable cgroups when the required controllers are unavailable.


I then moved to [cwt's Arch image](https://forum.rvspace.org/t/arch-linux-image-for-visionfive-2/1459), which has the cgroup controllers enabled. This is mostly because I spent hours trying to cross-compile a kernel following the instructions provided by VisionFive but none of these kernels are bootable.

```
user@starfive:~$ cat /sys/fs/cgroup/cgroup.subtree_control 
cpu cpuset io memory pids
```

With working `cpuset` I scheduled a Docker container on the node:

![](/images/nomad-riscv-schedule-task.png)

```hcl
job "docker-test" {
  type = "batch"

  constraint {
    attribute = "${attr.cpu.arch}"
    value     = "riscv64"
  }
  task "uname-task" {
    driver = "docker"
    config {
      image = "hello-world"
    }
  }
}
```

and now I can finally run GH actions on it, via [github-act-runner](https://github.com/ChristopherHX/github-act-runner).

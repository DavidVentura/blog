import datetime
import json
import os
import subprocess
from dataclasses import dataclass

@dataclass
class RunConfig:
    vmm: str
    kernel: str
    mem: int
    vcpu: int
    hugepages: bool
    cmdline_extra: str

@dataclass
class Timing:
    boot_to_pid1: float
    req_to_kernel: float
    req_to_pid1: float

    def __repr__(self):
        return f'vm creation: {self.req_to_kernel:05.2f} ms, boot: {self.boot_to_pid1:05.2f} ms, all: {self.req_to_pid1:05.2f} ms'
def run(rc: RunConfig):
    fc_config = {
      "boot-source": {
        "kernel_image_path": rc.kernel,
        "boot_args": f"earlyprintk=serial,ttyS0 console=ttyS0,115200 panic=-1 reboot=t no_timer_check printk.time=1  cryptomgr.notests tsc=reliable 8250.nr_uarts=1 iommu=off pci=off mitigations=off root=/dev/vda {rc.cmdline_extra} quiet init=/magic"
      },
      "machine-config": {
        "vcpu_count": rc.vcpu,
        "backed_by_hugepages": rc.hugepages,
        "mem_size_mib": rc.mem
      },
      "drives": [{
        "drive_id": "rootfs",
        "path_on_host": "/home/david/git/lk/rootfs.ext4",
        "is_root_device": True,
        "is_read_only": False, # create /mem
      }],
      "network-interfaces": [{
        "iface_id": "net1",
        "guest_mac": "06:00:AC:10:00:02",
        "host_dev_name": "tap0"
      }]
    }
    with open('/tmp/asd.json', 'w') as fd:
        json.dump(fc_config, fd)
    try:
        os.remove('/tmp/pysock')
    except FileNotFoundError:
        pass
    command = [rc.vmm, '--boot-timer', '--no-api', '--config-file', '/tmp/asd.json', '--no-seccomp']
    # command = ['./run-direct.sh', rc.vmm, '/tmp/asd.json']
    s = subprocess.run(command, capture_output=True)
    assert s.stdout is not None

    vm_created = None
    pid1_start = None
    vm_requested = None
    for line in s.stdout.decode().splitlines():
        if 'VM Request' in line:
            date, _, _ = line.partition(' ')
            vm_requested = datetime.datetime.fromisoformat(date)
        if 'VM created' in line:
            date, _, _ = line.partition(' ')
            vm_created = datetime.datetime.fromisoformat(date)
        if 'Guest-boot-time' in line:
            date, _, _ = line.partition(' ')
            pid1_start = datetime.datetime.fromisoformat(date)

    assert pid1_start
    assert vm_created
    assert vm_requested
    boot_time_sec = (pid1_start- vm_created).total_seconds()
    start_time_sec = (pid1_start- vm_requested).total_seconds()
    req_time_sec = (vm_created- vm_requested).total_seconds()
    return Timing(boot_to_pid1=boot_time_sec*1000, req_to_kernel=req_time_sec*1000, req_to_pid1=start_time_sec*1000)


_ipcfg = 'ip=172.16.0.2::172.16.0.1:255.255.255.0:hostname:eth0:off'

def benchmark(rc: RunConfig, count=30):
    print(rc)
    res = []
    for _ in range(count):
        t = run(rc)
        res.append(t)

    kernel = sorted([r.boot_to_pid1 for r in res])
    vm = sorted([r.req_to_kernel for r in res])

    return {'kernel_boot': sum(kernel)/count, 'vm_creation': sum(vm)/count, 'total_time':sum(kernel)/count + sum(vm)/count}


def run_with_slow_cgroups():
    # https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md#linux-61-boot-time-regressions
    # base = smp
    base_res = benchmark(RunConfig(vmm='./firecracker-apipages',
                         kernel="./vmlinux-mini-smp",
                         mem=128,
                         vcpu=1,
                         hugepages=False,
                         cmdline_extra=''))

    # +net with 10ms delay
    net_res = benchmark(RunConfig(vmm='./firecracker-apipages',
                         kernel="./vmlinux-mini-smp",
                         mem=128,
                         vcpu=1,
                         hugepages=False,
                         cmdline_extra=f'{_ipcfg} ip.dev_wait_ms=10'))

    # smp details
    smp_res = {}
    for cores in [1, 2, 4]:
        smp_res[cores] = benchmark(RunConfig(vmm='./firecracker-apipages',
                                             kernel="./vmlinux-mini-smp",
                                             mem=128,
                                             vcpu=cores,
                                             hugepages=False,
                                             cmdline_extra=_ipcfg))

    # -smp
    no_smp_res = {}
    for cores in [1, 2, 4]:
        no_smp_res[cores] = benchmark(RunConfig(vmm='./firecracker-apipages',
                                        kernel="./vmlinux-mini",
                                        mem=128,
                                        vcpu=cores,
                                        hugepages=False,
                                        cmdline_extra=_ipcfg))
    # +populate
    populate = {}
    for vmm in ['./firecracker-pages-populate', './firecracker-apipages']:
        populate[vmm] = {}
        for huge in [False, True]:
            hstr = '2MB' if huge else '4KB'
            populate[vmm][hstr] = {}
            for memsize in [128, 1024, 2048]:
                populate[vmm][hstr][memsize] = benchmark(RunConfig(vmm=vmm,
                                                         kernel="./vmlinux-mini",
                                                         mem=memsize,
                                                         vcpu=1,
                                                         hugepages=huge,
                                                         cmdline_extra=_ipcfg))

    with open('results.json', 'w') as fd:
        json.dump({
            'base_res': base_res,
            'net_res': net_res,
            'populate': populate,
            'no_smp': no_smp_res,
            'smp': smp_res,
            }, fd, indent=4)
    # real    2m6.111s to execute

def run_with_fast_cgroups():
    no_smp = {}
    for mem in [128, 1024, 2048]:
        no_smp[mem] = benchmark(RunConfig(vmm='./firecracker-apipages',
                                        kernel="./vmlinux-mini",
                                        mem=mem,
                                        vcpu=1,
                                        hugepages=True,
                                        cmdline_extra=_ipcfg))
    with open('results-fast-cg.json', 'w') as fd:
        json.dump({
            'fast_cgroup_no_smp_res': no_smp,
            }, fd, indent=4)

run_with_fast_cgroups()

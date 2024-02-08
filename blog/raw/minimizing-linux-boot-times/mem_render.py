import matplotlib.pyplot as plt
import json
from pathlib import Path

here = Path(__file__).parent

inf =  here / 'results.json'
cgroups_fast = here / 'results-fast-cg.json'

data = json.load(inf.open())
data_cg = json.load(cgroups_fast.open())

smp_cpu = data['smp']
no_smp_cpu = data['no_smp']

baseline = data['populate']['./firecracker-apipages']['4KB']

populated_4k = data['populate']['./firecracker-pages-populate']['4KB']
populated_2M = data['populate']['./firecracker-pages-populate']['2MB']

normal_huge = data['populate']['./firecracker-apipages']['2MB']

cgroups_fast_huge = data_cg['fast_cgroup_no_smp_res']

def render_scatter_vmm_time():
    data = (here / 'vmm_time').open().read().splitlines()
    data = [float(d)*1000 for d in data]

    data_4k = (here / 'vmm_time_4k').open().read().splitlines()
    data_4k = [float(d)*1000 for d in data_4k]

    x = list(range(0, len(data)))

    _, axs = plt.subplots(1, 2, figsize=(8, 4), sharex=True)
    axs[0].set_title("Unsorted")
    axs[0].scatter(x, data)
    #axs[0][1].scatter(x, data_4k)
    axs[0].set_ylabel('ms')
    #axs[0][1].set_ylabel('ms')

    axs[1].set_title("Sorted by call duration")
    axs[1].scatter(x, sorted(data))
    #axs[1][1].scatter(x, sorted(data_4k))
    #plt.xlabel('Execution #')
    return plt

def render_lineplot(series: list, label="Memory Size (MB)", xticks=None, ymax=None):
    plt.figure(figsize=(8, 6))
    for s in series:
        plt.plot(s['vm_sizes'], s['times'], marker='o', linestyle='-', label=s['label'])
    plt.xlabel(label)
    plt.ylabel("Time to Boot (ms)")
    plt.grid(True)
    plt.ylim(ymin=0)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    if xticks is not None:
        plt.xticks(xticks)
    plt.legend()
    plt.tight_layout()
    plt.subplots_adjust(top=0.95) # default is 0.9, otherwise title is cropped

    return plt

def render_stacked_bar_chart(series: list, ymax: int):
    categories = [s['label'] for s in series]
    labels = [k for k in series[0].keys() if k != 'label']
    print(categories, labels)
    values = {}
    for s in series:
        vmm = []
        kb = []
        for k, v in s.items():
            if k == 'label': continue
            kb.append(v['kernel_boot'])
            vmm.append(v['vm_creation'])
        values[s['label']] = [vmm, kb]
    _, axs = plt.subplots(1, len(categories), figsize=(8, 6), sharex=True)

    width = 0.45

    x = list(range(len(labels))) # 0 1 2

    # Plotting each category
    for i, cat in enumerate(categories):
        # Heights for each label
        heights1 = values[cat][0]
        heights2 = values[cat][1]
        
        if len(categories) == 1:
            _ax = axs
        else:
            _ax = axs[i]
        _ax.bar(x, heights1, width, label='VM creation')
        _ax.bar(x, heights2, width, bottom=heights1, label='Kernel boot')
        
        _ax.set_title(cat)
        _ax.set_ylim(ymin=0, ymax=ymax)
        _ax.legend()
        if i == 0:
            _ax.set_ylabel('Boot time (ms)')

    plt.legend()
    plt.xticks(x, labels)
    plt.tight_layout()

    return plt
    
def transform(data: dict, measurement: str):
    keys = sorted([int(k) for k in data.keys()])
    return {'vm_sizes': keys,
            'times': [data[str(k)][measurement] for k in keys],
            }


plot = render_lineplot([
    {**transform(smp_cpu, 'kernel_boot'), 'label': 'Baseline'},
    ], label="vCPU count", xticks=[1,2,3,4], ymax=60)
plot.title("Kernel Boot time vs vCPU count (128MB)")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_time_vs_vcpu_count_smp.svg", format="svg")

plot = render_lineplot([
    {**transform(smp_cpu, 'kernel_boot'), 'label': 'SMP'},
    {**transform(no_smp_cpu, 'kernel_boot'), 'label': 'No-SMP'},
    ], label="vCPU count", xticks=[1,2,3,4], ymax=60)
plot.title("Kernel Boot time vs vCPU count (128MB)")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_time_vs_vcpu_count_no_smp.svg", format="svg")


plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    ])
plot.title("Kernel Boot time vs Memory usage")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_time_vs_memory_size_4k.svg", format="svg")

plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    {**transform(populated_4k, 'kernel_boot'), 'label': 'MAP_POPULATE'},
    ])
plot.title("Kernel Boot time with MAP_POPULATE")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_time_with_populate.svg", format="svg")

plot = render_stacked_bar_chart([
    {**baseline, 'label': 'Baseline'},
    {**populated_4k, 'label': 'MAP_POPULATE'},
    ], ymax=450)
plot.title("MAP_POPULATE")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_and_vm_creation_populate.svg", format="svg")


plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    {**transform(normal_huge, 'kernel_boot'), 'label': 'Hugepages (2MB)'},
    ])

plot.title("Kernel Boot time with hugepages")
plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_time_hugepages.svg", format="svg")

plot = render_stacked_bar_chart([
    {**baseline, 'label': 'Baseline'},
    {**normal_huge, 'label': 'Hugepages (2MB)'},
    ], ymax=80)

plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_and_vm_creation_hugepages.svg", format="svg")


plot = render_stacked_bar_chart([
    {**normal_huge, 'label': 'Hugepages (2MB)'},
    {**cgroups_fast_huge, 'label': 'Hugepages (2MB) + favordynmods'},
    ], ymax=50)

plot.savefig("blog/html/images/minimizing-linux-boot-times/boot_and_vm_creation_cgroups_hugepages.svg", format="svg")

plot = render_scatter_vmm_time()
plot.savefig("blog/html/images/minimizing-linux-boot-times/vmm_creation_variance.svg", format="svg", bbox_inches='tight')

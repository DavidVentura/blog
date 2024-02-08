import matplotlib.pyplot as plt
import sys
import json
from pathlib import Path

inf =  Path(sys.argv[1])

data = json.load(inf.open())
smp_cpu = data['smp']
no_smp_cpu = data['no_smp']

baseline = data['populate']['./firecracker-apipages']['4KB']

populated_4k = data['populate']['./firecracker-pages-populate']['4KB']
populated_2M = data['populate']['./firecracker-pages-populate']['2MB']

normal_huge = data['populate']['./firecracker-apipages']['2MB']

def render_lineplot(series: list, label="Memory Size (MB)", xticks=None, ymax=None):
    plt.figure(figsize=(8, 6))
    for s in series:
        plt.plot(s['vm_sizes'], s['times'], marker='o', linestyle='-', label=s['label'])
    plt.xlabel(label)
    plt.ylabel("Time to Boot (ms)")
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
    plt.grid(True)
    plt.ylim(ymin=0)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    if xticks is not None:
        plt.xticks(xticks)
    plt.legend()

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
        
        axs[i].bar(x, heights1, width, label='VM creation')
        axs[i].bar(x, heights2, width, bottom=heights1, label='Kernel boot')
        
        axs[i].set_title(cat)
        axs[i].set_ylim(ymin=0, ymax=ymax)
        axs[i].legend()
        if i == 0:
            axs[i].set_ylabel('Boot time (ms)')

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
plot.savefig("blog/html/images/extreme-cgi-bin/boot_time_vs_vcpu_count_smp.png", format="png")

plot = render_lineplot([
    {**transform(smp_cpu, 'kernel_boot'), 'label': 'SMP'},
    {**transform(no_smp_cpu, 'kernel_boot'), 'label': 'No-SMP'},
    ], label="vCPU count", xticks=[1,2,3,4], ymax=60)
plot.title("Kernel Boot time vs vCPU count (128MB)")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_time_vs_vcpu_count_no_smp.png", format="png")


plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    ])
plot.title("Kernel Boot time vs Memory usage")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_time_vs_memory_size_4k.png", format="png")

plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    {**transform(populated_4k, 'kernel_boot'), 'label': 'MAP_POPULATE'},
    ])
plot.title("Kernel Boot time with MAP_POPULATE")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_time_with_populate.png", format="png")

plot = render_stacked_bar_chart([
    {**baseline, 'label': 'Baseline'},
    {**populated_4k, 'label': 'MAP_POPULATE'},
    ], ymax=450)
plot.title("MAP_POPULATE")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_and_vm_creation_populate.png", format="png")


plot = render_lineplot([
    {**transform(baseline, 'kernel_boot'), 'label': 'Baseline'},
    {**transform(normal_huge, 'kernel_boot'), 'label': 'Hugepages (2MB)'},
    ])

plot.title("Kernel Boot time with hugepages")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_time_hugepages.png", format="png")

plot = render_stacked_bar_chart([
    {**baseline, 'label': 'Baseline'},
    {**normal_huge, 'label': 'Hugepages (2MB)'},
    ], ymax=80)

plot.title("Hugepages")
plot.savefig("blog/html/images/extreme-cgi-bin/boot_and_vm_creation_hugepages.png", format="png")

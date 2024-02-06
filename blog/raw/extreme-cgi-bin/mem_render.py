import matplotlib.pyplot as plt
import sys
from pathlib import Path

out = Path(sys.argv[1])
# Sample data for memory size (in MB) and corresponding boot time (in seconds)
memory_sizes = [128, 1024, 4096]
boot_times_small = [15, 26.5, 62.56]
boot_times_huge = [9.6, 13.2, 21.9]
boot_times = boot_times_huge

# Create the line chart
plt.figure(figsize=(8, 6))
plt.plot(memory_sizes, boot_times_small, marker='o', linestyle='-')
#plt.plot(memory_sizes, boot_times_small, marker='o', linestyle='-', label='4kB pages')
#plt.plot(memory_sizes, boot_times_huge, marker='o', linestyle='-', label='2MB pages')

# Customize the chart
# plt.title("Boot Time vs. Memory Size")
plt.xlabel("Memory Size (MB)")
plt.ylabel("Time to Boot (ms)")
#plt.xticks([0, 128, 1024, 2048, 3072, 4096])
plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
plt.grid(True)
#plt.legend()

# Show the chart
#plt.show()
plt.savefig(out, format=out.suffix.strip('.'))

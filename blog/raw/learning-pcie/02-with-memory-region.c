#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/units.h"
#include "hw/pci/pci.h"
#include "hw/hw.h"
#include "hw/pci/msi.h"
#include "qemu/timer.h"
#include "qom/object.h"
#include "qemu/main-loop.h" /* iothread mutex */
#include "qemu/module.h"
#include "qapi/visitor.h"

#define TYPE_PCI_GPU_DEVICE "gpu"
#define GPU_DEVICE_ID         0x1337
typedef struct GpuState GpuState;
DECLARE_INSTANCE_CHECKER(GpuState, GPU,
                         TYPE_PCI_GPU_DEVICE)

struct GpuState {
    PCIDevice pdev;
    MemoryRegion mem;
	unsigned char data[0x100000];
};

static void pci_gpu_register_types(void);
static void gpu_instance_init(Object *obj);
static void gpu_class_init(ObjectClass *class, void *data);
static void pci_gpu_realize(PCIDevice *pdev, Error **errp);
static void pci_gpu_uninit(PCIDevice *pdev);

type_init(pci_gpu_register_types)

static void pci_gpu_register_types(void)
{
    static InterfaceInfo interfaces[] = {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    };
    static const TypeInfo gpu_info = {
        .name          = TYPE_PCI_GPU_DEVICE,
        .parent        = TYPE_PCI_DEVICE,
        .instance_size = sizeof(GpuState),
        .instance_init = gpu_instance_init,
        .class_init    = gpu_class_init,
        .interfaces = interfaces,
    };

    type_register_static(&gpu_info);
}

static void gpu_instance_init(Object *obj)
{
    printf("GPU instance init\n");
}

static void gpu_class_init(ObjectClass *class, void *data)
{
    printf("Class init\n");
    //DeviceClass *dc = DEVICE_CLASS(class);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(class);

    k->realize = pci_gpu_realize;
    k->exit = pci_gpu_uninit;
    k->vendor_id = PCI_VENDOR_ID_QEMU;
    k->device_id = GPU_DEVICE_ID;
    k->class_id = PCI_CLASS_OTHERS;
}

static uint64_t gpu_mem_read(void *opaque, hwaddr addr, unsigned size) {
	GpuState *gpu = opaque;
	uint64_t got = gpu->data[addr] & ((size <<3)-1);
    printf("Tried to read 0x%x bytes at 0x%lx = 0x%lx\n", size, addr, got);
    return got;
}
static void gpu_mem_write(void *opaque, hwaddr addr, uint64_t val, unsigned size) {
	GpuState *gpu = opaque;
	uint64_t sizedval = val & ((size<<3)-1);
	gpu->data[addr] = sizedval;
    printf("Tried to write 0x%lx [0x%lx] (0x%x bytes) at 0x%lx\n", val, sizedval, size, addr);

}
static const MemoryRegionOps gpu_mem_ops = {
    .read = gpu_mem_read,
    .write = gpu_mem_write,
};

static void pci_gpu_realize(PCIDevice *pdev, Error **errp)
{
    printf("GPU Realize\n");
    GpuState *gpu = GPU(pdev);
    memory_region_init_io(&gpu->mem, OBJECT(gpu), &gpu_mem_ops, gpu, "gpu-mem", 1 * MiB);
    pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &gpu->mem);
}

static void pci_gpu_uninit(PCIDevice *pdev)
{
    printf("GPU un-init\n");
}

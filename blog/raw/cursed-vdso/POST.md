---
title: Cursing a process' vDSO for time hacking
date: 2022-11-30
tags: cursed, rust
description: Replacing time-related vDSO entries at runtime
---

We found... unexpected behavior on Python's `Event` object: if the system's clock moves backwards while an `Event` is being waited on, 
it will seemingly hang "forever".

```python
Event.wait(5)  # time moves backwards during these 5 seconds
```

So I started digging on [CPython's source code](https://github.com/python/cpython) to try and find the reason why.

```python
class Event:
    def __init__(self):
        self._cond = Condition(Lock())
    ...
    def wait(self, timeout=None):
        ...
        signaled = self._cond.wait(timeout)
        ...

```
The `Event` class initializes a `Condition` and later executes `wait` on it.

```python
class Condition:
    ...
    def wait(self, timeout=None):
        ...
        waiter = _allocate_lock()
        ...
        if timeout > 0:
            gotit = waiter.acquire(True, timeout)
```

Where `Condition` itself waits by executing `acquire` on `waiter`, which is just an alias to `_thread.allocate_lock`

I couldn't find any exact matches for `allocate_lock` but this fuzzy match is promising
```c
PyThread_type_lock PyThread_allocate_lock(void);
```

There are some functions that act on a `PyThread_type_lock`, but `acquire_lock_timed` seems like the best match for the scenario

```c
PyLockStatus PyThread_acquire_lock_timed(PyThread_type_lock lock, PY_TIMEOUT_T microseconds, int intr_flag) {
...
    if (microseconds > 0) {
#ifdef HAVE_SEM_CLOCKWAIT
        monotonic_abs_timeout(microseconds, &ts);
#else
        MICROSECONDS_TO_TIMESPEC(microseconds, ts);
...
#endif
    }

    while (1) {
        if (microseconds > 0) {
		... // wait
	}
	}
}

```

Here's the first suspicious bit: `MICROSECONDS_TO_TIMESPEC` most definitely looks like something that will be affected by the system clock rewinding, 
as it is defined as a macro around `gettimeofday`

```c
#define MICROSECONDS_TO_TIMESPEC(microseconds, ts) \
do { \
    struct timeval tv; \
    gettimeofday(&tv, NULL); \
    tv.tv_usec += microseconds % 1000000; \
    tv.tv_sec += microseconds / 1000000; \
    tv.tv_sec += tv.tv_usec / 1000000; \
    tv.tv_usec %= 1000000; \
    ts.tv_sec = tv.tv_sec; \
    ts.tv_nsec = tv.tv_usec * 1000; \
} while(0)
```

Turns out, our CPython was not built with `HAVE_SEM_CLOCKWAIT` because we use glibc2.17 (from ~2012, yay CentOS).

The solution to the _actual_ problem we are facing is to either use [glibc \>2.30 (2019)](https://github.com/python/cpython/issues/85876#issuecomment-1093882569) or not use `Event.wait()` with a timeout, and instead use a different waiting mechanism.

We opted to go with using a different mechanism, which is pretty crude but sufficient for now:
```python
for i in range(0, timeout):
    if event.is_set():
        break
    time.sleep(1)
```

---

So, how to test that the bug is fixed? We could've introduced the same bug if `time.sleep` used `gettimeofday` internally!

A proper test is complicated: changing the system clock usually requires root permissions and is not trivial to execute in CI, so we have to resort to mocking.

There are some existing projects that deal with this:

* [freezegun](https://github.com/spulec/freezegun) has a nice user API, but only mocks calls coming from Python code, leaving us without validating whether we are using "unsafe" functions from CPython itself.
* [python-libfaketime](https://github.com/simon-weber/python-libfaketime) also has a nice API, and as it is based on [libfaketime](https://github.com/wolfcw/libfaketime), it manages to also mock the calls done by CPython itself.

**However.**

libfaketime ends up being _extremely janky_, as it is uses `LD_PRELOAD` to override symbols:

* The process must be re-executed with `LD_PRELOAD` set
    * This requires a shared object to be placed on disk, for the linker to pick up.
* As there is no method of coordination between the pre-loaded object and user's code,  communication is done via environment variables or files in the user's home.


The goal for today is to replace `gettimeofday` (and friends) with something that:

* Does not require the `LD_PRELOAD` trick
* Is user-space controllable

## The vDSO

`gettimeofday` is an external function, provided by a shared library coming from the kernel: the ["vDSO"](https://en.wikipedia.org/wiki/VDSO) (virtual, dynamic shared object).

The kernel automatically maps this shared library into the address space of all programs, which do not know that this is happening, they merely resolve external symbols (in this case `gettimeofday`) to a function they can call.

The point of the vDSO mechanism is to speed up some system calls: there is overhead on executing a syscall due to context-switching into the kernel, and this vastly dominates the time it takes to execute the actual requested function.

By mapping these functions directly to userspace, the context switch is bypassed and the necessary time to execute `gettimeofday` drops dramatically.

As this function must be dynamically loaded into the process at startup, all the information for linking should be available to the process itself, and indeed it is mapped in its own special region (`[vdso]`):

```bash
$ grep vdso /proc/self/maps
7ffd9f1d1000-7ffd9f1d3000 r-xp 00000000 00:00 0                          [vdso]
```

In this example, the vDSO memory is mapped in the range `0x7ffd9f1d1000-0x7ffd9f1d3000`, with permissions to read and execute (but **not** write, this is a standard security practice called [W^X](https://en.wikipedia.org/wiki/W%5EX)).

We can write a small program that reads its own vDSO memory mapping range and writes it out to disk, so we'll be able to look at it

```bash
$ ./extract_vdso > output && file output
output: ELF 64-bit LSB shared object, x86-64, version 1 (SYSV), dynamically linked, stripped
```

The vDSO memory area is in [ELF](https://en.wikipedia.org/wiki/Executable_and_Linkable_Format) format, which can be scanned for dynamic symbols:

```bash
$ objdump -T output
DYNAMIC SYMBOL TABLE:
0000000000000c10  w   DF .text	0000000000000005  LINUX_2.6   clock_gettime
0000000000000bd0 g    DF .text	0000000000000005  LINUX_2.6   __vdso_gettimeofday
0000000000000c20  w   DF .text	0000000000000060  LINUX_2.6   clock_getres
0000000000000c20 g    DF .text	0000000000000060  LINUX_2.6   __vdso_clock_getres
0000000000000bd0  w   DF .text	0000000000000005  LINUX_2.6   gettimeofday
0000000000000be0 g    DF .text	0000000000000029  LINUX_2.6   __vdso_time
0000000000000cb0 g    DF .text	000000000000009c  LINUX_2.6   __vdso_sgx_enter_enclave
0000000000000be0  w   DF .text	0000000000000029  LINUX_2.6   time
0000000000000c10 g    DF .text	0000000000000005  LINUX_2.6   __vdso_clock_gettime
0000000000000000 g    DO *ABS*	0000000000000000  LINUX_2.6   LINUX_2.6
0000000000000c80 g    DF .text	0000000000000025  LINUX_2.6   __vdso_getcpu
0000000000000c80  w   DF .text	0000000000000025  LINUX_2.6   getcpu
```

Each of these symbols is _just a function_ that can be called, and at the same time they are _just some bytes in memory_, which we _could_ write.

The steps could be summarized as:

* Find the vDSO memory range by scanning `/proc/self/maps`.
* Read the vDSO ELF blob.
* Overwrite vDSO area with a user-provided function.

## Find the process' vDSO address

Thanks to the [proc filesystem](https://en.wikipedia.org/wiki/Procfs), a process can inspect its own metadata very easily; `/proc/self/maps` contains all the relevant information
in an easy-to-parse, whitespace-delimited, format (trimmed down):

| Address                         |Perms|Offset  |Path|
|---------------------------------|-----|--------|------------|
|`5604dff9a000-5604dff9c000` | `r--p` |000000|/usr/bin/cat|
|`5604e121d000-5604e123e000` | `rw-p` |000000|[heap]|
|`7f38a9bd8000-7f38a9c02000` | `r-xp` |002000|ld-linux-x86-64.so.2|
|`7fff378cb000-7fff378ec000` | `rw-p` |000000|[stack]|
|`7fff3794f000-7fff37953000` | `r--p` |000000|[vvar]|
|`7fff37953000-7fff37955000` | `r-xp` |000000|[vdso]|

Where each line represents a single, contiguous range.

## Parsing the vDSO

In a similar vein, we can read our own memory at `/proc/self/mem`, skip ahead to the vDSO range (based on the `/proc/self/maps` metadata) and read the vDSO ELF blob. Thanks to the [goblin](https://docs.rs/goblin/latest/goblin/index.html) crate, interpreting these bytes as a walkable structure is trivial.

The ELF format ([1](https://www.caichinger.com/elf.html), [2](https://linuxhint.com/understanding_elf_file_format/), [3](https://wiki.osdev.org/ELF)) is reasonable and greatly documented[^1].

A short summary of the ELF format, that only covers the parts relevant for this task:

* There is a `Program Header Table`, which holds an array of `Program Header`.
* Each `Program Header` points to a `Section Header Table`
* Each `Section Header Table` holds an array of `Section Header`
* Each `Section Header` points to a `Section`
* Each `Section` holds an array of `Symbol`
* Each `Symbol` has:
    * Name: an _offset_ into the `STRTAB`
    * Size: the amount of bytes of code
    * Address: the offset, **relative to the start of the ELF**, where the first byte of program is.

This is probably better explained via a diagram:

![](/images/elf.png)


After extraction, this is what some symbols look like:

```rust
DynSym { name: "clock_gettime", address: 3088, size: 5 },
DynSym { name: "__vdso_gettimeofday", address: 3024, size: 5 },
```

where address is just the offset from the start of the ELF, not including the vDSO address in memory.

## Calling functions by address

Having the address of a function and its signature, is all that's really needed to execute a function.

As an example, calling a 

```rust
extern "C" my_gettimeofday(tp: *mut libc::timeval, tz: *mut c_void) {
    // ...
};

// Virtual Address of the function
let fptr = my_gettimeofday as *const ();

// Assign a type to the function, so the compiler will let us call it
let code: extern "C" fn(tp: *mut libc::timeval, tz: *mut c_void) =
    unsafe { std::mem::transmute(fptr) };

// Call the function
(code)(&mut tv, std::ptr::null_mut());

// Observe the result
println!(
    "called mygettimeofday manually {} {}",
    tv.tv_sec, tv.tv_usec
);
```

This worked as expected! We can now attempt to directly call the addresses obtained from the vDSO, if it works, it will validate the mechanism used to extract it.

We can replace `fptr` in the previous example:

```rust
let fptr = ((vdso_range.start as u64) + dynsym.address) as *const ();
```

Which also worked!


## Overwrite the vDSO

We now know:

* How to extract dynamic symbols from the vDSO
    * The name and address of the interesting symbols
* How to call functions by address (if we know the signature)

With this knowledge, we should be able to overwrite some vDSO symbols with our own code, something like:

```rust
let addr = (vdso_range.start as u64) + dynsym.address;
unsafe {
    std::ptr::write_bytes((addr + 0) as *mut u8, 0xC3, 1); // RET
}
```

This code, sadly, immediately exits the program, with return code 139 (Segmentation Fault).

Writing to this memory address wasn't allowed by the operating system.

From the memory map, we knew the process has no write permissions to the vDSO pages:
```bash
$ grep vdso /proc/self/maps
7ffd9f1d1000-7ffd9f1d3000 r-xp 00000000 00:00 0                          [vdso]
```

but the process should be the _owner_ of these pages, and able to change the permissions.

```rust
unsafe {
    libc::mprotect(
        r.start as *mut libc::c_void,
        r.end - r.start,
        libc::PROT_EXEC | libc::PROT_WRITE | libc::PROT_READ,
    );
}
```

Verifying that the `write` bit is set[^2]
```bash
$ grep vdso /proc/self/maps
7ffd9f1d1000-7ffd9f1d3000 rwxp 00000000 00:00 0                          [vdso]
```

With the pages being writable, we can attempt to write on the vDSO again:

```rust
let addr = (vdso_range.start as u64) + dynsym.address;
unsafe {
    std::ptr::write_bytes((addr + 0) as *mut u8, 0xC3, 1); // RET
    std::ptr::write_bytes((addr + 1) as *mut u8, 0x90, 15); // NOP
}
```
Which succeeds! We can dump the state of the vDSO before and after to verify the changes:

Before:

```objdump
<__vdso_clock_gettime@@LINUX_2.6>:
 c10:	e9 9b fb ff ff       	jmp    7b0 <LINUX_2.6@@LINUX_2.6+0x7b0>
 c15:	66 66 2e 0f 1f 84 00 	data16 cs nop WORD PTR [rax+rax*1+0x0]
 c1c:	00 00 00 00 
```

After:

```objdump
<__vdso_clock_gettime@@LINUX_2.6>:
 c10:	c3                   	ret
 c11:	90                   	nop
 c12:	90                   	nop
 c13:	90                   	nop
 c14:	90                      nop
 ...
```

Now the only thing left is actually placing our function in this area.

**However.**

These symbols must be multiples of the ${ELF-sector alignment} in size.

In this case that is 16 bytes, and some of the symbols are **just 16 bytes**, drastically limiting the functions that can be placed in this space.

I thought about modifying the ELF itself and re-writing the vDSO to have as much space as necessary, but that would also shift the following symbols and, generally, any code that has already run might have kept a reference to the the original function address around, which wouldn't work anymore.

What we **can** do with 16 bytes though, is building a [trampoline](https://en.wikipedia.org/wiki/Trampoline_(computing)) and use it to land in an "unrestricted-size" function.

This, conceptually, is very easy: overwrite the code to execute with a single `jmp $DST` instruction. In practice, I had a bunch of problems:

* In `x86_64`, you [can't jump](https://www.felixcloutier.com/x86/jmp) to an _absolute_ address that's represented as an immediate, it must be either of {indirect, relative, in a register}
* There's [a million](https://www.felixcloutier.com/x86/mov) opcodes for MOV, it really wasn't clear which one I should use

So I cheated, and let `nasm` and `objdump` deal with it for me; wrote

```asm
   global  _start
   section .text
_start:
   mov	   rax, 0x12ff34ff56ff78ff
   jmp 	   rax
```

Which `nasm -f elf64` compiled for me, and `objdump -M intel` dumped:

```objdump
<_start>:
   0:   48 b8 ff 78 ff 56 ff    movabs rax,0x12ff34ff56ff78ff
   7:   34 ff 12 
   a:   ff e0                   jmp    rax
```

The function to overwrite the vDSO now looks like this:
```rust
// MOV RAX, <address>
std::ptr::write_bytes((addr + 0) as *mut u8, 0x48, 1);
std::ptr::write_bytes((addr + 1) as *mut u8, 0xB8, 1);
std::ptr::copy(&dst_address as *const u64, (addr + 2) as *mut u64, 1);
// JMP
std::ptr::write_bytes((addr + 10) as *mut u8, 0xFF, 1);
std::ptr::write_bytes((addr + 11) as *mut u8, 0xE0, 1);
// NOP the remaining space, unnecessary, but useful when debugging
std::ptr::write_bytes((addr + 12) as *mut u8, 0x90, padding_size);
```
Re-dumped a modified vDSO and got...

```objdump
<__vdso_clock_gettime@@LINUX_2.6>:
 c10:   48 b8 30 4f 87 bb 65    movabs rax,0x5565bb874f30                                  
 c17:   55 00 00                                                                           
 c1a:   ff e0                   jmp    rax                                                 
 c1c:   90                      nop                                                        
 c1d:   90                      nop
 c1e:   90                      nop                                                        
 c1f:   90                      nop
```

Success!!

Now that we can jump into any user-controlled address, we only need to write code that matches the original function signatures:
```rust
extern "C" fn my_gettimeofday(tp: *mut libc::timeval, _tz: *mut c_void) {
    if !tp.is_null() {
        unsafe {
            (*tp).tv_sec = 666;
            (*tp).tv_usec = 999;
        }
    }
}
```

This works! Any caller to `gettimeofday` within this rust program (or anything linking this crate) will see time coming from this function.


## User provided functions

While a PoC that returns a constant was a lot of work, it's also pretty useless. 

I'm not entirely sure of what's the proper way to do this -- the `extern` functions that are the trampoline's targets can't be closures, so for now I'm using `static` variables (there is only _one_ `gettimeofday` anyway).

```rust
type ClockGetTimeOfDayCb = fn() -> TimeVal;

lazy_static! {
    static ref CLOCK_GTOD_CB: RwLock<Option<ClockGetTimeOfDayCb>> = RwLock::new(None);
}
```

If a user passes a function matching the signature specified in `ClockGetTimeOfDayCb`, we can proxy the `gettimeofday` call back to them:

```rust
extern "C" fn my_gettimeofday(tp: *mut libc::timeval, _tz: *mut c_void) {
    // TODO: Support TZ
    if !tp.is_null() {
        let res = CLOCK_GTOD_CB.read().unwrap().unwrap()();
        unsafe {
            (*tp).tv_sec = res.seconds;
            (*tp).tv_usec = res.micros;
        }
    }
}
```

This is what I set out to achieve, so I'm calling it a success!

---

## Python bindings

As a bit of an extra, I made a separate crate with Python bindings, via [PyO3](https://github.com/PyO3/pyo3), which now lives at [py-tpom](https://github.com/DavidVentura/py-tpom), and can show the usefulness of such a thing:

```python
def test_time_changes():
    target = datetime(2012, 1, 14, 1, 2, 3)
    assert datetime.now() != target
    with Freezer(target):
        assert datetime.now() == target
    assert datetime.now() != target
```


You can find the source code [here](https://github.com/davidVentura/tpom).

[^1]: [dumpelf](https://linux.die.net/man/1/dumpelf) is great for understanding ELF
[^2]: this is just an example, `grep` has its own vDSO with its own status

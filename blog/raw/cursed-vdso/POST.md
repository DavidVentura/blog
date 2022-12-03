---
title: Cursing a process' vDSO for time hacking
date: 2022-11-30
tags: cursed, rust
description: Replacing time-related vDSO entries at runtime
incomplete: false
---

We found a bug on Python's `Event` object: if the system's clock moved backwards while an `Event` was being waited on, 
it would seemingly hang "forever".

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

The solution to the _actual_ problem we are facing is to either use [glibc >2.30 (2019)](https://github.com/python/cpython/issues/85876#issuecomment-1093882569) or not use `Event.wait()` with a timeout, and instead use a different waiting mechanism.

We opted to go with using a different mechanism, which is pretty crude but sufficient for now:
```python
for i in range(0, timeout):
    if event.is_set():
        break
    time.sleep(1)
```
So, how to test that the bug is fixed? We could've introduced the same bug if `time.sleep` used `gettimeofday` internally!

A proper test is complicated: changing the system clock requires root permissions, and it's not trivial to execute in CI, so we have to resort to mocking.

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

As `gettimeofday` is a [vDSO](https://en.wikipedia.org/wiki/VDSO) function call (and _not_ a syscall), all the necessary information about vDSO is in the process memory space.

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

* Find the vDSO memory range by scanning /proc/self/maps
* Read the vDSO ELF blob
* Overwrite vDSO area with a user-provided function

## Find the process' vDSO range

Thanks to the [proc filesystem](https://en.wikipedia.org/wiki/Procfs), a process can inspect its own metadata very easily; `/proc/self/maps` contains all the relevant information
in an easy-to-parse, whitespace-delimited, format (trimmed down):

| Address                         |Perms|Offset  |Path|
|---------------------------------|-----|--------|------------|
|`5604dff9a000-5604dff9c000`|`r--p`|000000|/usr/bin/cat|
|`5604e121d000-5604e123e000`|`rw-p`|000000|[heap]|
|`7f38a9bd8000-7f38a9c02000`|`r-xp`|002000|ld-linux-x86-64.so.2|
|`7fff378cb000-7fff378ec000`|`rw-p`|000000|[stack]|
|`7fff3794f000-7fff37953000`|`r--p`|000000|[vvar]|
|`7fff37953000-7fff37955000`|`r-xp`|000000|[vdso]|

Where each line represents a single, contiguous range.

## Parsing the vDSO ELF blob

In a similar vein, we can read our own memory at `/proc/self/mem`, skip ahead to the vDSO range (based on the `/proc/self/maps` metadata) and read the vDSO ELF blob. Thanks to the [goblin](https://docs.rs/goblin/latest/goblin/index.html) crate, interpreting these bytes as a walkable structure is trivial.

The [ELF Format](https://www.caichinger.com/elf.html) is reasonable, though there are some things to keep in mind to extract the data we want

The Elf Format defines a set of sections, and some of them contain partial information

```
  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al
  [ 0]                   NULL            0000000000000000 000000 000000 00      0   0  0
  [ 1] .hash             HASH            0000000000000120 000120 000048 04   A  3   0  8
  [ 2] .gnu.hash         GNU_HASH        0000000000000168 000168 00005c 00   A  3   0  8
  [ 3] .dynsym           DYNSYM          00000000000001c8 0001c8 000138 18   A  4   1  8
  [ 4] .dynstr           STRTAB          0000000000000300 000300 00008b 00   A  0   0  1
  [ 5] .gnu.version      VERSYM          000000000000038c 00038c 00001a 02   A  3   0  2
  [ 6] .gnu.version_d    VERDEF          00000000000003a8 0003a8 000038 00   A  4   2  8
  [ 7] .dynamic          DYNAMIC         00000000000003e0 0003e0 000120 10  WA  4   0  8
  [11] .text             PROGBITS        00000000000006e0 0006e0 00066c 00  AX  0   0 16
```

The symbols we are interested in are dynamic, and we want to extract two things for each of them: their name and address (to know what to overwrite and where).

The information in the `DYNSYM` table has:

* name: the index on the dynamic string table
* value: the offset of this symbol from the section's virtual address
* size: size in bytes of the symbol
    * though the actual space taken by the symbol is `max(size, section.alignment)`

the dynamic string table is a null-delimited bag of bytes
```
__vdso_gettimeofday\0__vdso_time\0__vdso_clock_gettime\0__vdso_clock_getres\0...
       ^ "gettimeofday" would point to this index
^ "__vdso_gettimeofday" would point to this index
```

Example:

```rust
DynSym { name: "clock_gettime", address: 3088, size: 5 },
DynSym { name: "__vdso_gettimeofday", address: 3024, size: 5 },
```

where address is dynsym addr + symbol offset, not including the vDSO addr in memory

we now can call the vDSO function by address

## Calling functions by address

```rust
let fptr = my_gettimeofday as *const ();
let code: extern "C" fn(tp: *mut libc::timeval, tz: *mut c_void) =
    unsafe { std::mem::transmute(fptr) };

(code)(&mut tv, std::ptr::null_mut());

println!(
    "called mygettimeofday manually {} {}",
    tv.tv_sec, tv.tv_usec
);
```

this worked as expected, so we can now validate the addresses obtained from the vDSO by calling them:

```rust
let fptr = ((vdso_range.start as u64) + dynsym.address) as *const ();
let code: extern "C" fn(tp: *mut libc::timeval, tz: *mut c_void) =
    unsafe { std::mem::transmute(fptr) };
(code)(&mut tv, std::ptr::null_mut());
println!("{} {}", tv.tv_sec, tv.tv_usec);
```

this also worked! the extraction of the addresses from the ELF blob is correct.


## Overwrite the vDSO

As we now know the name and address of each symbol, we should be able to overwrite them with our own code, something like:

```rust
let addr = (vdso_range.start as u64) + dynsym.address;
unsafe {
    std::ptr::write_bytes((addr + 0) as *mut u8, 0xC3, 1); // RET
}
```

this, sadly, immediately dies a horrible death by segfault -- writing to this address wasn't allowed.

From the memory map, we knew the process has no write permissions to the vDSO pages:
```bash
$ grep vdso /proc/self/maps
7ffd9f1d1000-7ffd9f1d3000 r-xp 00000000 00:00 0                          [vdso]
```
but the process _should_ be the owner of these pages, and able to change the permissions.

```rust
unsafe {
    libc::mprotect(
        r.start as *mut libc::c_void,
        r.end - r.start,
        libc::PROT_EXEC | libc::PROT_WRITE | libc::PROT_READ,
    );
}
```

Verifying that the `write` bit is set
```bash
$ grep vdso /proc/self/maps
7ffd9f1d1000-7ffd9f1d3000 rwxp 00000000 00:00 0                          [vdso]
```

After this, writing to the vDSO range succeeds! We can dump the state of the vDSO before and after to verify the changes:

Before:

```objdump
0000000000000c10 <__vdso_clock_gettime@@LINUX_2.6>:
 c10:	e9 9b fb ff ff       	jmp    7b0 <LINUX_2.6@@LINUX_2.6+0x7b0>
 c15:	66 66 2e 0f 1f 84 00 	data16 cs nop WORD PTR [rax+rax*1+0x0]
 c1c:	00 00 00 00 
```

After:

```objdump
0000000000000c10 <__vdso_clock_gettime@@LINUX_2.6>:
 c10:	c3                   	ret    
 c11:	9b                   	fwait                    ; this is a broken analysis by
 c12:	fb                   	sti                      ; objdump, the byte 9b is the samee
 c13:	ff                   	(bad)                    ; second byte as was present before
 c14:	ff 66 66             	jmp    *0x66(%rsi)       ; but it makes no sense by itself
 c17:	2e 0f 1f 84 00 00 00 	cs nopl 0x0(%rax,%rax,1) ; (after a ret), and breaks further
 c1e:	00 00                                            ; decoding
```

the first byte is `C3` (`RET`)!

Now the only thing left is placing our function in this area

**However.**

These blocks must be multiples of 16 (ELF sector alignment value)bytes in size, and some of them are **just 16 bytes**, drastically limiting the functions that can be placed in this space.

I thought about modifying the ELF and re-writing the vDSO to have more space, but that would also shift the following symbols and, generally, any code that has already run might have kept a reference to the the original function address around, which wouldn't work anymore.

What we **can** do with 16 bytes though is to put a [trampoline](https://en.wikipedia.org/wiki/Trampoline_(computing)), and use it to land in an "unrestricted" function.

This, conceptually is very easy, overwrite the code to execute with a single `jmp $DST` instruction. In practice, I had a bunch of problems:

* You [can't](https://www.felixcloutier.com/x86/jmp) jump to an _absolute_ address that's represented as an immediate, it must be either of {indirect, relative, in a register}
* There's [a million](https://www.felixcloutier.com/x86/mov) opcodes for MOV, it really wasn't clear which one I should use

So I cheated, and let `nasm` deal with it for me; wrote

```asm
        global  _start
        section .text
_start:
        mov		rax, 0x12ff34ff56ff78ff
        jmp 		rax
```

and got the opcodes from `nasm -f elf64`.. which I manually copied into my source code.

Re-dumped a modified vDSO and got...

```objdump
0000000000000c10 <__vdso_clock_gettime@@LINUX_2.6>:
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

This is what I set out to achieve, so I'm calling it a success! As a bit of an extra, I made a separate crate with Python bindings, via [PyO3](https://github.com/PyO3/pyo3), which now lives at [py-tpom](https://github.com/DavidVentura/py-tpom), and can show the usefulness of such a thing:

```python
def test_time_changes():
    target = datetime(2012, 1, 14, 1, 2, 3)
    assert datetime.now() != target
    with Freezer(target):
        assert datetime.now() == target
    assert datetime.now() != target
```


You can find the source code [here](https://github.com/davidVentura/tpom).

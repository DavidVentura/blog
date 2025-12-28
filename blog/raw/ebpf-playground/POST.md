---
title: Building ebpf.party
date: 2025-12-27
tags: ebpf, meta
slug: building-ebpf-party
incomplete: true
---

Years ago, I discovered [hackattic](https://hackattic.com/), and since then, I've had this line in my `project_ideas.md`:

> hackattic but ebpf

and this holiday season I finally had enough time to get started.

What I wanted, to build, was very concrete: eBPF based challenges, with a good user experience.

Why? Because every time I want to work on an eBPF-based project, it's a pain in the ass. The tools kinda suck,
the docs are not there. Mostly it boils down to:

- Read Linux source to try and understand
- Try some stuff and see if it works

In this post, I'm only going to cover my path through building [https://ebpf.party](ebpf.party), for actual eBPF content, go there.

## The plan

Let the user write a full eBPF program in C, run it for them, give them feedback.

Let's look at an example eBPF program to have some shared context, though the specifics don't matter now.

```c
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>

struct event {
    __u32 pid;
    __u32 ppid;
    __u32 old_pid;
    char filename[16];
};

struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(__u32));
    __uint(value_size, sizeof(__u32));
} events SEC(".maps");


SEC("tp/sched/sched_process_exec")
int handle_exec(struct trace_event_raw_sched_process_exec* ctx)
{
    struct event event = {};
    event.pid = ctx->pid;
    event.old_pid = ctx->old_pid;
    unsigned short offset = ctx->__data_loc_filename & 0xFFFF;
    bpf_probe_read_kernel_str(&event.filename, sizeof(event.filename), (void *)ctx + offset);

    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU, &event, sizeof(event));
    return 0;
}
```

This program will use ✨eBPF magic✨ to run the `handle_exec` function whenever a new process is executed.

If we imagine the user submitted this program, they will expect:

- Typecheck
- Compile
- Run
- Give feedback

Let's go down the list

## Checkning syntax and types

to even typecheck this program, we need to first create `vmlinux.h`

```bash
bpftool btf dump file /sys/kernel/btf/vmlinux format c > vmlinux.h
```
This is very convenient, and exports _all_ the core (TODO core?) types into one convenient header file, which means a 3MB monstrosity.


So, all sources are here. How do we provide a good typechecking experience? The user _could_ send whatever they've typed so far to the server
and get it type-checked remotely, but it's a pretty shitty experience.

Of course, the only possible answer then, is to parse and type-check it locally.

Parsing and type-checking are parts of the [frontend](https://en.wikipedia.org/wiki/Compiler#Front_end) of a compiler.

I don't want to implement a C compiler for this! Luckily [TCC, the tiny C compiler](https://bellard.org/tcc/) exists. TCC's main features
are being small and fast to compile.

How do we run TCC in the browser though? We can compile C to WASM with [emscripten](https://emscripten.org/).

Then we export a function to compile a string
```c
int check_syntax(const char *content) {
    TCCState *s = tcc_new();
    tcc_set_lib_path(s, ".");
    tcc_set_error_func(s, NULL, error_callback);
    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);

    int result = tcc_compile_string(s, content);
    tcc_delete(s);
    return result;
}
void error_callback(void *opaque, const char *msg) {
    fprintf(stderr, "%s\n", msg);
}
```

TCC is truly delightful.

To compile to WASM we only[^emcc_flags] need some flags on emcc

[^emcc_flags]: Actually, the `-O2` here is load-bearing, without it, dead code elimination won't run and we get linker errors.

```bash
emcc -sEXPORTED_FUNCTIONS=_check_syntax \
     -sEXPORTED_RUNTIME_METHODS=ccall \
     -DONE_SOURCE=1 -DTCC_TARGET_X86_64 \
     -o syntax_check.js -I. -O2 \
     libtcc.c tccpp.c tccgen.c tccasm.c x86_64-gen.c x86_64-link.c i386-asm.c \
     bindings.c
$ ls -lh syntax_check.*
298K syntax_check.wasm
 69K syntax_check.js
```

That's amazing!

In JS, we can call into the compiler with just

```javascript
const result = Module.ccall(
    'check_syntax', // fn
    'number', // ret
    ['string'], // arg types
    ["int main() { return 1; }"] // args
);
```

This is actually generating an in-memory ELF file, then throwing it away, which is a bit wasteful.

I stubbed out some code <TODO> and removed the codegen calls. <TODO timing>

As cool as this is, when adding an example with `#include "vmlinux.h"`, it takes roughly 50ms.

For this, I made a python script using libclang, that recursively extracts type definitions from a header (vmlinux.h) based
on some input types.

When giving the program the input types from the previous example, it creates a 700KB file, which is still way too much!
I needed to implement blacklisting of some audit/nfs/tty/xfrm types, and landed at a 400KB header, about 1/8th of the original size.

With this new header, compilation takes about 12ms.

I profiled TCC <TODO flamegraph> and about half the time is spent in malloc/free. I made a simple
patch to use an arena, and TCC is now roughly twice as fast <TODO flamegraph>

Caveat: I only benchmarked this on the native build, because I don't know how to do it in WASM.

A `console.log()` based debugging shows roughly 5ms to do a compile pass.

This is fast enough to run _on keypress_, but a bit unnecessary. I think running after 50-100ms of idle time should be good enough.

## Compiling to BPF

Once `tcc` says that the code is at least legal C, we need to compile it to a valid BPF ELF file.

This means that we need clang, and that's going to run on the server.

```bash
$ clang -O2 -target bpf -D__TARGET_ARCH_x86 -I/usr/include/bpf -c file.c -o output.bpf.o
$ ls -lh output.bpf.o
2.1K output.bpf.o
```

Compilation succeeds, but, if we run the generated `.o` file through a generic BPF loader (more on that later), the file is rejected:

```bash
$ sudo ./generic-loader output.bpf.o
Loading BPF object: output.bpf.o
libbpf: BTF is required, but is missing or corrupted.
Failed to open BPF object file
```

I was quite confused but eventually found [a GitHub issue](https://github.com/libbpf/libbpf/issues/667) that says you need debug info
for `libbpf` to load the binary.

Adding `-g` to clang's flags makes the file load, but look at this:

```bash
$ ls -lh output.bpf.o
495K output.bpf.o
```

Almost 500KB bigger, that's way too much. But why?

```bash
$ llvm-objdump -h output.bpf.o

Sections:
Idx Name                            Size     Type
  0                                 00000000
  1 .strtab                         0000013c
  2 .text                           00000000 TEXT
  3 tp/sched/sched_process_exec     00000420 TEXT
  4 .reltp/sched/sched_process_exec 00000010
  5 license                         00000004 DATA
  6 .rodata.str1.1                  00000006 DATA
  7 .maps                           00000018 DATA
  8 .debug_loclists                 000000b8 DEBUG
  9 .debug_abbrev                   0000031a DEBUG
 10 .debug_info                     0002a3ea DEBUG
 11 .rel.debug_info                 00000060
 12 .debug_rnglists                 0000003d DEBUG
 13 .debug_str_offsets              00009a60 DEBUG
 14 .rel.debug_str_offsets          00026960
 15 .debug_str                      0001eea6 DEBUG
 16 .debug_addr                     00000028 DEBUG
 17 .rel.debug_addr                 00000040
 18 .BTF                            000001f6
 19 .rel.BTF                        00000020
 20 .BTF.ext                        00000150
 21 .rel.BTF.ext                    00000120
 22 .debug_frame                    00000028 DEBUG
 23 .rel.debug_frame                00000020
 24 .debug_line                     000000ef DEBUG
 25 .rel.debug_line                 00000090
 26 .debug_line_str                 0000005e DEBUG
 27 .llvm_addrsig                   00000003
 28 .symtab                         00000180
```

That's a lot of `DEBUG` data!

Running the file through `llvm-strip --strip-debug` removes all the `DEBUG` sections, and we are left with a 3.1KB file, that `libbpf` accepts.

## Preparing to load BPF

I mentioned before a generic loader, this was a small utility I used to validate multiple BPF programs on my host system.

The details are not too interesting, but it boils down to

```c
obj = bpf_object__open_file(argv[1], NULL);
err = bpf_object__load(obj);
bpf_object__for_each_program(prog, obj) {
    const char *prog_name = bpf_program__name(prog);
    const char *sec_name = bpf_program__section_name(prog);

    printf("  - %s (section: %s) ... ", prog_name, sec_name);
    struct bpf_link *link = bpf_program__attach(prog);
}
```

However, in this scenario, we want to run the BPF program in a VM, not on my host system.

Also, we need to manage the VM from this program, send messages, thread, etc. Also, I don't want to add a dynamic linker on the VM.
I was not confident to do that in C.

Translating this code to Rust via [libbpf-rs](https://docs.rs/libbpf-rs/latest/libbpf_rs/) was easy, and it mostly looks the same:

```rust
let open_obj = ObjectBuilder::default().open_memory(program).unwrap();
let obj = open_obj.load().unwrap();
let mut links: Vec<_> = Vec::new();
for p in obj.progs_mut() {
    let link = p.attach().unwrap();
    links.push(link); // unloads on Drop
}
```

So far so good, but! By default, the `libbpf-sys` link dynamically, which I really don't want.

Luckily, the `libbpf-sys` crate offers a _bunch_ of knobs to control the build, including static compilation.

The only problem is that _their dependencies_, namely, libelf, does not build statically. I think these are bugs.

When building _libraries_ the files `color.c` and `printversion.c` are pulled in, which in turn, pull `argp_parse`, a glibc
symbol for argument parsing. We don't need that in a library.


Remove the files from the makefile
```patch
diff --git a/lib/Makefile.am b/lib/Makefile.am
index b3bb929f..0bb2789d 100644
--- a/lib/Makefile.am
+++ b/lib/Makefile.am
@@ -35,7 +35,11 @@ noinst_LIBRARIES = libeu.a

 libeu_a_SOURCES = xasprintf.c xstrdup.c xstrndup.c xmalloc.c next_prime.c \
                  crc32.c crc32_file.c \
-                 color.c error.c printversion.c
+                 error.c
```

When trying to build, configure bails:

```text
checking for library containing argp_parse... no

configure: WARNING: compiler doesn't generate build-id by default
configure: error: in `/home/david/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/libbpf-sys-1.6.2+v1.6.2/elfutils':
configure: error: failed to find argp_parse
See `config.log' for more details
```

so we need to patch the configure file as well, to not bail if libs are not found

```patch
diff --git a/configure.ac b/configure.ac
index bbe8673e..e099c83b 100644
--- a/configure.ac
+++ b/configure.ac
@@ -635,16 +641,6 @@ AC_COMPILE_IFELSE([AC_LANG_SOURCE([])],
 CFLAGS="$old_CFLAGS"])
 AS_IF([test "x$ac_cv_fno_addrsig" = "xyes"], CFLAGS="$CFLAGS -fno-addrsig")

-saved_LIBS="$LIBS"
-AC_SEARCH_LIBS([argp_parse], [argp])
-LIBS="$saved_LIBS"
-case "$ac_cv_search_argp_parse" in
-        no) AC_MSG_FAILURE([failed to find argp_parse]) ;;
-        -l*) argp_LDADD="$ac_cv_search_argp_parse" ;;
-        *) argp_LDADD= ;;
-esac
-AC_SUBST([argp_LDADD])
-
 saved_LIBS="$LIBS"
 AC_SEARCH_LIBS([fts_close], [fts])
 LIBS="$saved_LIBS"
@@ -655,16 +651,6 @@ case "$ac_cv_search_fts_close" in
 esac
 AC_SUBST([fts_LIBS])

-saved_LIBS="$LIBS"
-AC_SEARCH_LIBS([_obstack_free], [obstack])
-LIBS="$saved_LIBS"
-case "$ac_cv_search__obstack_free" in
-        no) AC_MSG_FAILURE([failed to find _obstack_free]) ;;
-        -l*) obstack_LIBS="$ac_cv_search__obstack_free" ;;
-        *) obstack_LIBS= ;;
-esac
-AC_SUBST([obstack_LIBS])
-
 dnl The directories with content.

 dnl Documentation.
```

With this patch and a slightly involved set of CFLAGS, it will build statically:

```bash
LIBBPF_SYS_EXTRA_CFLAGS="-idirafter /usr/include/x86_64-linux-gnu -idirafter /usr/include" \
    cargo build --target x86_64-unknown-linux-musl
```


## Loading BPF

We now have a generic, static BPF loader and a BPF ELF file.

We need somewhere to run it. I've written before about [how to use firecracker programatically](/posts/abusing-firecracker/),
and [how to boot Linux quickly](/posts/minimizing-linux-boot-times/), so I won't go into detail here.

When running this in a VM, with no other data on the filesystem, things immediately blew up:

```text
thread 'main' panicked at src/main.rs:160:71:
called `Result::unwrap()` on an `Err` value: Error: failed to open object from memory

Caused by:
    Function not implemented (os error 38)
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
```

Obviously my custom kernel has _some feature_ disabled, but what? I built [strace](https://github.com/strace/strace) statically
and run my program under it (kernel cmdline `init=/strace -- /loader output.bpf.o`)

strace gave me
```text
bpf(BPF_PROG_LOAD, {...}, 148) = -1 ENOSYS (Function not implemented)
```

Guess who had `CONFIG_BPF=n`? This guy.

After that, it died again immediately.

```text
faccessat2(AT_FDCWD, "/sys/kernel/debug/tracing", F_OK, AT_EACCESS) = -1 ENOENT (No such file or directory)
open("/sys/kernel/tracing/events/syscalls/sys_enter_execve/id", O_RDONLY|O_LARGEFILE|O_CLOEXEC) = -1 ENOENT (No such file or directory)
```

I was confused with the `/sys/kernel/debug/tracing` check, the docs say

```text
CONFIG_TRACEFS_AUTOMOUNT_DEPRECATED:

The tracing interface was moved from /sys/kernel/debug/tracing
to /sys/kernel/tracing in 2015, but the tracing file system
was still automounted in /sys/kernel/debug for backward
compatibility with tooling.

The new interface has been around for more than 10 years and
the old debug mount will soon be removed.
```

if it's been 10 years, why is the new `libbpf` checking? I guess for compatibility? Regardless,
that was not the issue!

The actual problem is that I didn't mount tracefs at `/sys/kernel/tracing`.

After that, the program loaded.


## Returning results

just blobs of bytes

## Drawing the rest of the owl


### Mapping types

how??
use TCC to return types

bless C, types are globally unique.


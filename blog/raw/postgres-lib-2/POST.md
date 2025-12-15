---
date: 2025-12-15
incomplete: true
tags: postgres
title: Postgres lib 2
description: extension boogaloo
series: embedded-postgres
---

In the previous episode we got a Postgres server compiled to a static library, linked to a project, and got to execute some queries.

That's _fine_ but kids these days demand more. Postgres is seemingly just a contrived vessel onto which one should deploy all kinds of code.

By this, I mean [extensions](https://www.postgresql.org/docs/current/external-extensions.html).

In summary, if you can pack your code as a shared object (`.so` file), comply with a [simple ABI](https://www.postgresql.org/docs/current/xfunc-c.html#XFUNC-C-DYNLOAD)
and write two text files (`extension--version.sql` and `extension.control`), you can use a Postgres instance as your very own execution environment!

That's all nice, but what to do in the static library context?

## Loading an extension

The process for 'installing' an extension onto a database is roughly:

1. Run `CREATE EXTENSION <extension>`
1. Read `<extension>.control` from a very specific path
1. Execute `<extension>-<version>.sql` from a very specific path
1. Call `dlopen()` to load the `<extension>.so` file
1. Call `dlsym()` to find specific function pointers

The specific functions are `_PG_init`, and functions referenced in the `<extension>-<version>.sql` file.

The control file looks like this:
```text
comment = 'A comment'
default_version = '1.0'
relocatable = true
```

The SQL file looks like this:

```sql
CREATE FUNCTION add_one(integer) RETURNS integer AS 'example', 'add_one'
LANGUAGE C STRICT IMMUTABLE;
```

If we are building all of Postgres as a static lib, it makes little sense to build extensions as dynamic libraries (ignoring the fact that without a dynamic loader, manually loading a shared library is a pain in the ass), so, the only sane option is to build extensions as static libraries, along with Postgres.

If we take a very simple extension:
```c
#include "postgres.h"

PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(add_one); // this macro creates pg_finfo_add_one

Datum add_one(PG_FUNCTION_ARGS) {
	int32 arg = PG_GETARG_INT32(0);
	PG_RETURN_INT32(arg + 1);
}
void _PG_init(void) {
	elog(NOTICE, "Example static extension initialized");
}
```
Building it is trivial (`musl-gcc -static -I../src -o example.a`), but how to plug it into Postgres?

Well, we can make a registry of extensions in-process

```c
typedef struct StaticExtensionLib {
    struct StaticExtensionLib *next;
    const char *library;
    PG_init_t init_func;
    bool init_called;
    const StaticExtensionFunc *functions;
    const StaticExtensionFInfo *finfo_functions;
} StaticExtensionLib;
```

then, each extension needs a little bit of code to register itself

```c
const StaticExtensionFunc example_static_functions[] = {
    {"add_one", add_one},
    {NULL, NULL}
};

const StaticExtensionFInfo example_static_finfo[] = {
    {"pg_finfo_add_one", pg_finfo_add_one},
    {NULL, NULL}
};

void register_example(void) {
    register_static_extension(
        "example",
        _PG_init,
        example_static_functions,
        example_static_finfo
    );
}
```

but of course, just creating some 'registry' doesn't mean that postgres will do anything, we need to patch Postgres a little bit:

In `src/backend/utils/fmgr/dfmgr.c`:
```diff
 void *
 load_external_function(const char *filename, const char *funcname,
                        bool signalNotFound, void **filehandle) {
-   // the entire function body
+   return pg_load_external_function(filename, funcname, signalNotFound, filehandle);
 }

 void *
 lookup_external_function(void *filehandle, const char *funcname) {
-   return dlsym(filehandle, funcname);
+   return pg_lookup_external_function(filehandle, funcname);
 }
```

`pg_lookup_external_function` is nothing special: walk the linked list and return the function pointer if the name matches.


Let's try it

```c
pg_embedded_exec("CREATE EXTENSION example");
result = pg_embedded_exec("SELECT add_one(41)");
printf("Result: %s\n", result->values[0][0]);
```

gives
```
Result: 42
```

## Loading _two_ extensions

The static build system works great, but if we add a second extension there's a small problem. You know how the extension ABI requires you to declare `_PG_init`? Well, if you have two extensions, you have two `_PG_init` symbols.

In the dynamic library world, this is not a problem, because `dlsym` takes a `handle` parameter, effectively namespacing the symbol.

In our static world, we just get a linker error:

```
extension_static.c: multiple definition of `_PG_init'; ../extension/example/example.a(example.o): first defined here
```

This is easy enough to fix, we can rename the symbol with `objcopy`[^rename]

```bash
objcopy --redefine-sym=_PG_init=example_PG_init example.o;
```

Why `objcopy` instead of renaming `_PG_init`? Well, I want to build existing extensions unmodified, instead of keeping patches.

## Building _all_ the extensions

For the previous extensions, I've manually added the necessary little bit of code to get them 'registered' with postgres, I mean this:

```c
const StaticExtensionFunc example_static_functions[] = {...};
const StaticExtensionFInfo example_static_finfo[] = {...};
void register_example(void) { };
```
and it was _fine_ for my toy extension, but then I got to `pgvector`, which exports 104 functions, and I'm not doing that manually.

My solution for this? Build the extension statically into `<extension>.a`, then list all the symbols, and conveniently the ABI requires every symbol to be accompanied by a meta function, which has the prefix `pg_finfo_`.

So, I made a python script that essentially runs `nm <extension>.a` and generates some C code that looks like 

```c
#include "postgres.h"
#include "fmgr.h"
#include "extensions.h"

extern Datum hamming_distance(PG_FUNCTION_ARGS);
extern Datum jaccard_distance(PG_FUNCTION_ARGS);
extern Datum array_to_halfvec(PG_FUNCTION_ARGS);
// ...

extern const Pg_finfo_record *pg_finfo_hamming_distance(void);
extern const Pg_finfo_record *pg_finfo_jaccard_distance(void);
extern const Pg_finfo_record *pg_finfo_array_to_halfvec(void);
// ...

extern void vector_PG_init(void);

const StaticExtensionFunc vector_static_functions[] = {
	{"hamming_distance", hamming_distance},
	{"jaccard_distance", jaccard_distance},
	{"array_to_halfvec", array_to_halfvec},
    // ...
}

void
register_vector(void) {
	register_static_extension(
		"vector",
		vector_PG_init,
		vector_static_functions,
		vector_static_finfo
	);
}
```

note that this file has `extern void vector_PG_init` -- it links to the objcopy-renamed symbol.

With this file, I can generate _another_ static library, `<extension>_static.a`, which is the one I finally link to Postgres.

### A detour on pgvector and PGXS

When trying to build `pgvector` statically for my extension, I had some issues because it depends on `pgxs` in its `Makefile`:
```
PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
```

The PGXS included Makefile is _thousands_ of lines long, pulls a version of clang I don't have installed and hardcodes `-shared`.

I didn't feel like debugging/patching it, so I did not use it. Instead of thousands of lines of Makefile, I used 14 lines of bash:

```bash
CC="${CC:-musl-gcc}"
CFLAGS="${CFLAGS:--static -fPIC}"
INCLUDE_DIR="${INCLUDE_DIR:-../pl/vendor/pg18/src/include}"
OUTPUT_LIB="${OUTPUT_LIB:-libvector.a}"
OPTFLAGS="-march=native -ftree-vectorize -fassociative-math -fno-signed-zeros -fno-trapping-math"
FULL_CFLAGS="$CFLAGS -I$INCLUDE_DIR $OPTFLAGS"
SOURCES=(src/*.c)

rm -f src/*.o

for src in "${SOURCES[@]}"; do
    obj="${src%.c}.o"
    $CC $FULL_CFLAGS -c "$src" -o "$obj" &
done
wait

ar rcs "$OUTPUT_LIB" src/*.o
```

## Postgres and its fixation with random files


here need to do the timezonesets stuff, then note that i avoided mentioning extensions only work because i carefully placed .sql and .control files in appropriate paths

---
date: 2025-12-15
tags: postgres
title: Postgres lib 2
description: extension boogaloo
series: Embedded postgres server
slug: postgres-extensions
---

In the previous episode we got a Postgres server compiled to a static library, linked to a project, and got to execute some queries.

That's _fine_ but kids these days demand more. Postgres is seemingly just a contrived vessel onto which one should deploy all kinds of code.

By this, I mean [extensions](https://www.postgresql.org/docs/current/external-extensions.html).

In summary, if you can pack your code as a shared object (`.so` file), comply with a [simple ABI](https://www.postgresql.org/docs/current/xfunc-c.html#XFUNC-C-DYNLOAD)
and write two text files (`extension--version.sql` and `extension.control`), you can use a Postgres instance as your very own computing environment!

That's nice, but the `.so` extensions are meant to be dynamically loaded by a process. What can we do in a static library context?

## Loading an extension

When a user runs `CREATE EXTENSION <extension>`, the server will:

1. Read `<extension>.control` from a very specific path
1. Execute `<extension>-<version>.sql` from a very specific path
1. Call `dlopen()` to load the `<extension>.so` file
1. Call `dlsym()` to find some function pointers by name

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

when this is executed, the server will:

- Run the `_PG_init` function
- Keep a mapping of the string `add_one` to the function pointer from the library

This `dlopen`/`dlsym` mechanism doesn't really work in a static library context.

Even ignoring the fact that without a dynamic loader, manually loading a shared library is a pain in the ass, 
it makes little sense to build extensions as dynamic libraries -- the flexibility gained by decoupling deployment of the database vs extensions is not really worth the extra complexity.

So, the only sane option is to build extensions as part of the Postgres static library.

Let's take a trivial extension:

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

Building it is trivial (`musl-gcc -static -I../src -o example.a`), but how to plug it into the static Postgres?

What we need is fairly simple. Per library, keep a mapping: function name &rarr; function pointer

The easiest way to do that, is to have a linked-list of metadata for each extension

```c
typedef struct StaticExtensionLib {
    struct StaticExtensionLib *next;
    const char *library; // "pgvector", "example", ...
    PG_init_t init_func;
    bool init_called;
    const StaticExtensionFunc *functions;
    const StaticExtensionFInfo *finfo_functions;
} StaticExtensionLib;
```

Each extension needs to add itself to the list of extensions. If we use the previous 'example' extension:

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

but of course, just creating some 'registry' doesn't mean that Postgres will magically use it. We need to replace the
dynamic extension loading with code that will look in the registry:

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

In summary:
- We built a trivial extension (`example.c`) into a static library (`example.a`)
- We linked the extension (`example.a`) along with postgres (`libpostgres.a`)
- We had some code call `register_example` to add the extension functions to a global registry
- We patched Postgres to look into the global registry instead of doing `dlopen`/`dlsym`

With all of this in place, when `SELECT add_one(41)` was executed, our `add_one` function got called.

## Loading _two_ extensions

The static build system works great, but if we add a second extension there's a small problem. You know how the extension ABI requires you to declare `_PG_init`? Well, if you have two extensions, you have two `_PG_init` symbols.

In the dynamic library world, this is not a problem, because `dlsym` takes a `handle` parameter, effectively namespacing the symbol.

In our static world, we just get a linker error:

```
extension_static.c: multiple definition of `_PG_init'; ../extension/example/example.a(example.o): first defined here
```

This is easy enough to fix, we can rename the symbol:

```bash
objcopy --redefine-sym=_PG_init=example_PG_init example.o;
```

Why `objcopy` instead of renaming `_PG_init` in the `example.c` file? Well, I want to build existing extensions unmodified, instead of keeping patches.

## Building _all_ the extensions

For the previous extensions, I've manually added the necessary little bit of code to get them 'registered' with postgres, I mean this:

```c
const StaticExtensionFunc example_static_functions[] = {...};
const StaticExtensionFInfo example_static_finfo[] = {...};
void register_example(void) { };
```
and it was _fine_ for my toy extension, but then I got to `pgvector`, which exports 104 functions, and I'm not doing that manually.

My solution for this? Build the extension statically into `<extension>.a`, then list all the symbols.

Not _every_ symbol in the archive file is a function for Postgres to call though. Helper functions shouldn't be added to the static registry.

How to tell extensions and helper functions apart? Well, _conveniently_ the ABI requires every extension function to be accompanied by a meta function, which has the prefix `pg_finfo_`.

So, I made a python script that essentially runs `nm <extension>.a | grep pg_finfo` and generates a _wrapper_ static library which looks like 

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


TODO: is this clear without a diagram

### A detour on pgvector and PGXS

When trying to build `pgvector` statically for my extension, I had some issues because it depends on `pgxs` in its `Makefile`:

```make
PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
```

The PGXS included Makefile is _thousands_ of lines long, pulls a version of Clang I don't even have installed and even _dares_ hardcode `-shared` when calling `clang`.

I didn't feel like patching it, so I did not use it. Instead of thousands of lines of Makefile, I used 14 lines of bash:

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

With this, `pgvector` loaded, and worked just fine:

```c
pg_embedded_exec("CREATE EXTENSION vector");
pg_embedded_exec("CREATE TABLE items (id bigserial PRIMARY KEY, embedding vector(3))");
pg_embedded_exec("INSERT INTO items (embedding) VALUES ('[1,2,3]'), ('[4,5,6]')");
result = pg_embedded_exec("SELECT * FROM items ORDER BY embedding <-> '[3,1,2]' LIMIT 5");
for (int row = 0; row < result->rows; row++)
    printf("  id: %s, embedding: %s\n", result->values[row][0], result->values[row][1]);
```
Which prints
```text
Found 5 results:
  id: 1, embedding: [1,2,3]
  id: 2, embedding: [4,5,6]
```

<div class="aside">
I do not understand the point in <code>pgxs</code>. It seems to "simplify" building with the correct flags. What does <em>correct</em> mean?? Am I expected to build the extension on the same host
where my database is running???
</div>

## Making the library self contained

Up to this point, everything works fine, but it requires a carefully crafted filesystem, as Postgres expects some files to be available on-disk.

When building the library, I'm passing `--prefix=/tmp/pg-embedded-install`, and if that directory is empty, Postgres will log

```text
ERROR: could not open directory "/tmp/pg-embedded-install/share/postgresql/timezonesets":
No such file or directory
```

and refuse to start.

<div class="aside">
I initially spent some time trying to parse the `timezonesets/Default` file at compile time, but it was harder than expected—this helper depends on _most_ of Postgres, and it would require patching out
quite a bit of parsing code, but I am trying _quite_ hard to keep the patchset for Postgres small.
</div>

My solution for this was to wrap specific `AllocateFile` calls (Postgres version of `fopen`) with a some code that checks if the filename is `Default` and just returns a `const char*` with the data preloaded.

Once this is in place, the database starts up again, without `/tmp/pg-embedded-install` present on the host.

However, now extensions don't work! Trying to load an extension fails and logs

```text
ERROR: Query failed: extension "example" is not available
```

Tracing a little bit, I found a bunch of `stat` and `AllocateFile` calls, looking for `<extension>.control` and `<extension>--<ver>.sql` in `<PREFIX>/share/postgresql/extension/`. These little bits of path are hardcoded across parts of the codebase, so changing it is not really feasible.

For extensions, I ended up patching `extension.c`

```diff
-	if (stat(filename, &fst) == 0)
+	if (has_embedded_file(filename) || stat(filename, &fst) == 0)
```
and
```diff
-	if ((file = AllocateFile(filename, "r")) == NULL)
+	if ((file = embedded_AllocateFile(filename, "r")) == NULL)
```

```diff
-	src_str = read_whole_file(filename, &len);
+	src_str = get_embedded_file_data(filename, &len) || read_whole_file(filename, &len);
```

these are repeated a total of 5 times.

To do this, I had to update the extension registry a little bit, by adding two 'file' members to `StaticExtensionLib`:

```c
const EmbeddedFile *control_file;
const EmbeddedFile *script_file;
```

where `EmbeddedFile` is just
```c
typedef struct EmbeddedFile {
	const char *filename;
	const unsigned char *data;
	unsigned int len;
} EmbeddedFile;
```

and `embedded_AllocateFile` does `fmemopen` to return a `FILE*` from `const char*` 🤮

It's _nasty_, but now we don't need any files on the host besides the database cluster directory!


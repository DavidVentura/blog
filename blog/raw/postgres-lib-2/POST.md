---
date: 2025-12-16
tags: postgres, cursed
title: Building extensions into libpostgres
description: the dynamic linker is for the weak
series: Embedded postgres server
slug: postgres-extensions
---

<link href="/css/telegram.css" rel="stylesheet" type="text/css"/>

In the previous episode we got a Postgres server compiled to a static library, linked to a project, and got to execute some queries.

That's _fine_ but Kids These Days demand more. Postgres has seemingly become just a contrived vessel onto which one should deploy all kinds of code.

By this, I mean [extensions](https://www.postgresql.org/docs/current/external-extensions.html).

In summary, if you can pack your code as a shared object (`.so` file), comply with a [simple ABI](https://www.postgresql.org/docs/current/xfunc-c.html#XFUNC-C-DYNLOAD)
and write two text files (`extension--version.sql` and `extension.control`), you can use a Postgres instance as your very own computing environment!

That's nice, but the `.so` extensions are meant to be dynamically loaded by a process. What can we do in a static library context?

## Loading an extension

When a user runs `CREATE EXTENSION <extension>`, the server will:

1. Read `<extension>.control` from a very specific path
1. Execute `<extension>-<version>.sql` from the same specific path
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

- Run the `_PG_init` function from the extension's `.so`
- Keep a mapping of the string `add_one` to the function pointer from the library

At least, that's the case in a normal Postgres server, with dynamically loaded extensions.

## Dynamic loader, who?

This `dlopen`/`dlsym` mechanism doesn't really work in a static context.

Without a loader (`ld.so`), manually loading a shared library is a pain in the ass. Even putting that aside,
it makes little sense to build extensions as dynamic libraries -- the flexibility gained by decoupling deployment of the database vs extensions is not worth the extra complexity.

My friend Mårten is with me on this one:

<div class="chat">
   <div class="message-from" data-timestamp="23:48"><span>you are a smart man</span></div>
   <div class="message-from" data-timestamp="23:48"><span>what's the smart man's alternative to dlopen</span></div>
   <div class="message-to"   data-timestamp="23:49"><span>No dynamic</span></div>
   <div class="message-to"   data-timestamp="23:50"><span>Include the .a in your gcc command</span></div>
</div>

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

Building it is trivial (`musl-gcc -static -I../src -c example.c -o example.o`), but how to plug it into the static Postgres?

What we need is fairly simple: for each library, keep a mapping of function name &rarr; function pointer

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
register_example();
pg_embedded_exec("CREATE EXTENSION example"); // _PG_init will be called
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

With all of this in place, when `SELECT add_one(41)` was executed, the `add_one` function got called.

## Loading _two_ extensions

The static build system works great, but if we add a second extension there's a small problem. You know how the extension ABI requires the `_PG_init` and `Pg_magic_func` functions? Well, if you have two extensions, you will have two definitions of each!

In the dynamic library world, this is not a problem, because `dlsym` takes a `handle` parameter, effectively namespacing the symbol.

In our static world, we just get linker errors:

```
extension_static.c: multiple definition of `_PG_init'; ../extension/example/example.a(example.o): first defined here
extension_static.c: multiple definition of `Pg_magic_func'; ../extension/example/example.a(example.o): first defined here
```

This is easy enough to fix, we can rename the `_PG_init` symbol and make `Pg_magic_func` file-local:

```bash
objcopy --redefine-sym=_PG_init=example_PG_init \
        --localize-symbol=Pg_magic_func example.o
```

Why `objcopy` instead of renaming `_PG_init` in the `example.c` file? Well, I want to build existing extensions unmodified, instead of keeping patches.

What about `Pg_magic_func`? This function is used to verify that both Postgres and the extension agree on the ABI. We are compiling them statically into the same bundle, so they will always agree.

## Building _all_ the extensions

For the previous extensions, I've manually added the necessary little bit of code to get them 'registered' with postgres, I mean this:

```c
const StaticExtensionFunc example_static_functions[] = {...};
const StaticExtensionFInfo example_static_finfo[] = {...};
void register_example(void) { };
```
and it was _fine_ for a toy extension, but then I got to [pgvector](https://github.com/pgvector/pgvector), which exports 104 functions. No way I'm doing that manually.

Since the ABI _conveniently_ requires every extension function to have a companion `pg_finfo_` meta function, we can programmatically filter for extension functions from the archive (`<extension>.a`).

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

Something like this:

<center>
    <img src="assets/Page-2.svg" style="width: 35rem; max-width: 100%" />
</center>

There's nothing that _yet another layer of indirection_ can't beat.

### A detour on pgvector and PGXS

When trying to build `pgvector` statically for my extension, I had issues with its build system, specifically, because it uses `pgxs` in its `Makefile`:

```make
PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
```

The PGXS included Makefile is _thousands_ of lines long, pulls a version of Clang I don't even have installed and even _dares_ hardcode `-shared` when calling `clang`.

I didn't feel like patching it, so I did not use it. Instead of thousands of lines of Makefile, I used this little script:

```bash
set -eu
INCLUDE_DIR="${INCLUDE_DIR:-../pl/vendor/pg18/src/include}"
OUTPUT_LIB="${OUTPUT_LIB:-libvector.a}"
SOURCES=(src/*.c)

for src in "${SOURCES[@]}"; do
    obj="${src%.c}.o"
    $CC $CFLAGS -I$INCLUDE_DIR -c "$src" -o "$obj" &
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
  id: 1, embedding: [1,2,3]
  id: 2, embedding: [4,5,6]
```

<div class="aside">
I do not understand the point in <code>pgxs</code>. It seems to "simplify" building with the correct flags. What does <em>correct</em> mean?? Am I expected to build the extension on the same host
where my database is running???
</div>

## Making the library self contained

Up to this point, everything works fine, as long as it's running on a carefully crafted filesystem. This is because Postgres expects some non-database files to be available on-disk.

When building the library, I'm passing `--prefix=/tmp/pg-embedded-install`, and if that directory is empty, Postgres will log

```text
ERROR: could not open directory "/tmp/pg-embedded-install/share/postgresql/timezonesets":
No such file or directory
```

and refuse to start.

<div class="aside">
I initially spent some time trying to parse the <code>timezonesets/Default</code> file at compile time, but it was harder than expected—this helper depends on <em>most</em> of Postgres, and it would require patching out
quite a bit of parsing code, but I am trying <em>quite</em> hard to keep the patchset for Postgres small.
</div>

My solution for this was to wrap specific `AllocateFile` calls (Postgres' version of `fopen`) with some code that checks if the filename is `Default` and just returns a `const char*` with the data preloaded.

Once this is in place, the database starts up again, without `/tmp/pg-embedded-install` present on the host.

However, now extensions don't work! Trying to load an extension fails and logs

```text
ERROR: Query failed: extension "example" is not available
```

Tracing a little bit, I found a bunch of `stat` and `AllocateFile` calls, looking for `<extension>.control` and `<extension>--<ver>.sql` in `<PREFIX>/share/postgresql/extension/`. These little bits of path are hardcoded across parts of the codebase, so changing it is not really feasible.

Like before, I'd rather embed these constant values into `.rodata` than read them from the filesystem.

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

`control_file` and `script_file` are generated by the script when it generates `<extension>_static.c`.

and `embedded_AllocateFile` does `fmemopen` to return a `FILE*` from `const char*` 🤮

It's _nasty_, but now we don't need any files on the host besides the database cluster directory!

Pgvector was a good testing ground, time to spice it up.

## PostGIS

[PostGIS](https://postgis.net/) is an extension for Postgres that processes spatial data; it's fairly popular, and a quick skim of its build system
tells me it's not going to go gentle into that good ~~night~~ archive.

Like `pgvector`, `PostGIS` uses `pgxs` and a fairly complex build system. As far as I understood, the minimal dependency tree looks like:

```text
PostGIS
  GEOS
  PROJ
    SQLite
  libxml2
```

Yep, that's right, if you load the PostGIS extension, _some of your Postgres queries will depend on SQLite_.

The resulting build script is quite straightforward, but it took me a few hours of hair-pulling.

### Building PostGIS dependencies

Building [GEOS](https://libgeos.org/)
```bash
cmake -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
      -DBUILD_TESTING=OFF \
      -DBUILD_GEOSOP=OFF \
      -DCMAKE_C_COMPILER="$CC" \
      -DCMAKE_CXX_COMPILER="$CXX" \
      ..
```

Building [PROJ](https://proj.org/en/stable/)
```bash
cmake -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
      -DENABLE_TIFF=OFF \
      -DENABLE_CURL=OFF \
      -DBUILD_TESTING=OFF \
      -DBUILD_APPS=OFF \
      -DCMAKE_C_COMPILER="$CC" \
      -DCMAKE_CXX_COMPILER="$CXX" \
      -DSQLite3_INCLUDE_DIR="$SQLITE_DIR" \
      -DSQLite3_LIBRARY="$SQLITE_DIR/libsqlite3.a" \
      ..
```


[SQLite](https://sqlite.org/), as always, is a delight
```bash
$CC -O2 -fPIC -DSQLITE_OMIT_LOAD_EXTENSION -c sqlite3.c -o sqlite3.o
```

Building [libxml2](https://gitlab.gnome.org/GNOME/libxml2)
```bash
./autogen.sh --prefix=/usr --disable-shared --enable-static --with-pic --without-python --without-lzma --without-zlib
make -j8 libxml2.la
```

### Building PostGIS itself

This is a little bit more complicated, I don't think they were optimizing for "ease of building without our build system".

The core of the build script (summarized) looks something like this

```bash
INCLUDES="-I$PG_INCLUDE"
INCLUDES="$INCLUDES -I../$POSTGIS_DIR/liblwgeom"
INCLUDES="$INCLUDES -I../$POSTGIS_DIR/libpgcommon"
INCLUDES="$INCLUDES -I../$POSTGIS_DIR/deps/ryu/.."
INCLUDES="$INCLUDES -I../$POSTGIS_DIR/deps/flatgeobuf"
INCLUDES="$INCLUDES -I../$POSTGIS_DIR/deps/flatgeobuf/include"
INCLUDES="$INCLUDES -I../$POSTGIS_DIR"
INCLUDES="$INCLUDES -I../$GEOS_CAPI_INCLUDE"
INCLUDES="$INCLUDES -I../$XML_INCLUDE"
DEFINES="-DHAVE_GEOS=1 -DHAVE_LIBPROJ=1 -DHAVE_LIBXML2=1"

for srcdir in "liblwgeom" "liblwgeom/topo" "libpgcommon" "deps/ryu" "postgis"; do
    prefix=$(basename "$srcdir")
    for src in ../$POSTGIS_DIR/$srcdir/*.c; do
        $CC $CFLAGS $INCLUDES $DEFINES -c "$src" -o "${prefix}_$(basename "$src" .c).o" &
    done
done

# ew
for src in ../$POSTGIS_DIR/deps/flatgeobuf/*.cpp; do
    $CXX $CXXFLAGS $INCLUDES -c "$src" -o "flatgeobuf_$(basename "$src" .cpp).o" &
done

wait

ar rcs "../bare_postgis.a" *.o
```

This creates `bare_postgis.a` which does not have the dependencies bundled, for that, I wrote a small `ar` script (did you know that `ar` supports scripting?):

```text
CREATE libpostgis_all.a
ADDLIB bare_postgis.a
ADDLIB $VENDOR_DIR/geos/build/lib/libgeos_c.a
ADDLIB $VENDOR_DIR/geos/build/lib/libgeos.a
ADDLIB $VENDOR_DIR/proj/build/lib/libproj.a
ADDLIB $VENDOR_DIR/sqlite/libsqlite3.a
ADDLIB $VENDOR_DIR/libxml2/.libs/libxml2.a
SAVE
END
```

which I then ran with `ar -M`.

This creates a 45MB `libpostgis_all.a`.

To convert this library to the 'static registry' format we discussed before, we need both the `.control` and `.sql` files.

This was... unexpectedly difficult. The `.sql` file is generated with an unholy combination of C preprocessor macros and `perl`.

After pushing through all of this, we are greeted by a beautiful sight:
```text
-- SELECT PostGIS_Full_Version();
postgis ver='POSTGIS="3.6.2dev 11021e0" [EXTENSION] PGSQL="180" GEOS="3.12.2-CAPI-1.18.2" (compiled against GEOS 0.3.12) PROJ="9.5.1" (compiled against PROJ 0.9.0) LIBXML="20912"'
```

Though it did increase the size of the compiled binary by 17MB. Oof.

If we create some more meaningful data:
```sql
CREATE TABLE locations (id SERIAL PRIMARY KEY, name TEXT, geom GEOMETRY(Point, 4326));

INSERT INTO locations (name, geom) VALUES
  ('San Francisco', ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326)),
  ('New York', ST_SetSRID(ST_MakePoint(-74.0060, 40.7128), 4326)),
  ('London', ST_SetSRID(ST_MakePoint(-0.1278, 51.5074), 4326));
```

When running a query like this
```sql
SELECT l1.name, l2.name, ROUND(ST_Distance(l1.geom::geography, l2.geom::geography) / 1000)::integer AS distance_km
FROM locations l1, locations l2
WHERE l1.name = 'San Francisco' AND l2.name != 'San Francisco'
ORDER BY distance_km";
```

The DB logs

```text
proj_create: Cannot find proj.db
proj_create: no database context specified
proj_create_operation_factory_context: Cannot find proj.db
pj_obj_create: Cannot find proj.db
proj_coordoperation_is_instantiable: Cannot find proj.db
pj_obj_create: Cannot find proj.db
```

... but still gives a result?

```text
New York,4139 km
London,8639 km
```

The missing `proj.db` lines seem to be a common issue, as there's [an FAQ entry](https://proj.org/en/stable/faq.html#why-am-i-getting-the-error-cannot-find-proj-db) on PROJ's website about it.

There seem to be _some_ fallback values, as the query _did_ work. From some quick research, the magic number `4326` seems to be blessed with fallbacks. Other numbers are not so lucky.

Regardless, depending on the filesystem to do calculations is just silly.
Grepping for this message, I found `proj/src/iso19111/factory.cpp`, which is a cool 10052 lines.

I ended up replacing the `open` function body with:

```cpp
sqlite3 *embedded_db = get_embedded_proj_db();
if (!embedded_db)
    throw FactoryException("Cannot load embedded proj.db");
sqlite_handle_ = SQLiteHandle::initFromExisting(embedded_db, false, 0, 0);
databasePath_ = ":memory:";
```

where `get_embedded_proj_db` just calls `sqlite3_deserialize` on a `const char* db`. This `db` is generated by running the 9MiB(**!!**) `proj.db` through `xxd -include`.

This allows the extension to work without looking for the DB on disk, but it does bloat the binary size by another 9MiB.

Breaking it down, the self-contained `PostGIS` feature adds 26MiB to the binary:

- 9MiB for `proj.db`
- 7.2MiB for `postgis--3.6.2dev.sql`
- 9.8MiB of code

I did a quick test, and standard `gzip` can compress `proj.db` to 1.7MiB and `postgis--3.6.2dev.sql` to 0.5MB. Could save 14MB of `.rodata` someday.

## Wrapping up

Making extensions work in libpostgres was fun, but wrangling multiple build systems was not.

For some of these projects, I needed to write some patches, which I kept as `.patch` files on my repo. I don't know if this is a good strategy, and it feels like it won't work well if the patchset grows.

I'm not sure if there's a niche for this project. Developer experience is _pretty good_, but configuring Docker is not that hard.

It's definitely been a lot of (type-2) fun.

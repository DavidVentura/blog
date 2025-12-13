---
title: Postgres server as a library
date: 2025-12-09
tags: postgres
slug: postgres-library
description: global state was a mistake
---

I feel like I just woke up from a fever dream. I've spent a large chunk of my waking hours over the last 3 days deep in the Postgres codebase.

Why would you do that to yourself, you may ask. Well, I recently found out about [pglite](https://pglite.dev/), a project to build Postgres as a WASM(+WASI) blob
and use it as a library.

The thing is, I am weirdly driven by cursed projects and spite.

My love of cursedness made me into a WASM fan (LEB128 in an ISA? what could be more cursed than that!), but sometimes there's such a thing as too cursed, even for me. When they implemented variable-length-instructions for a _virtual ISA_, I joined the WASM-haters-club.

I have a much longer, much more concrete WASM rant in me, but it'll require some effort to write down, so now is not the time.

Back to Postgres and pglite—if they can build Postgres in WASM, then _surely_ it is possible to build it as a regular library (shared/static) and use it. I know nothing about postgres internals, but jumping in feet first has never gone wrong before.

## Building postgres statically

This is somehow the easiest part of the project

```bash
CC=musl-gcc CFLAGS="-static" LDFLAGS="-static" ./configure
```

Then make a static library with the `backend` object files

```bash
cd src/backend && ar crs libpostgres_server.a $(find -name objfiles.txt -exec cat {} \;)
```

then merge `libpostgres_server.a` with `libpgcommon_srv.a` and `libpgport_srv.a` (simplified)

```bash
mkdir .tmp && cd .tmp
ar x ../libpgcommon_srv.a # unpack
ar x ../libpgport_srv.a   # unpack
ar rcs ../libpostgres_server.a *.o # repack
```

and finally add some timezone object files into the archive:
```bash
ar rcs libpostgres_server.a src/timezone/localtime.o src/timezone/pgtz.o src/timezone/strftime.o
```

This gives a ~100MB static file with 875 object files inside, a lot of them are unused, but that's ok.

## Analyzing Postgres startup

Postgres is usually compiled to a binary (`postgres`) that runs as a server (`postmaster`) and `fork()`s a new process to handle each connection.

_Surely_ it should be possible to bypass the whole server/connection dance and just execute the query code directly.

Around this point is where about 16 hours of my weekend disappeared. What I thought would be "just call some function" became "read through all paths of postgres initialization behavior and see how it affects global state".

Why? Because even though postgres is one of the pieces of technology keeping the world together, it started as a university project 30&ndash;35 years ago, and it shows. There is _significant_ global state, seemingly everything I touched wanted to read or write from it.

I assume that because a bunch of state is global, Postgres relies on `fork()` to execute parts of code that need to temporarily modify the global state.



It turns out that postgres has [single user mode](https://www.postgresql.org/docs/18/app-postgres.html#APP-POSTGRES-SINGLE-USER) which does exactly this, all we need to do is somehow call this code directly.

The plan is to emulate single-user mode by performing _some_ amount of setup, then querying the DB directly via the [Server Programming Interface](https://www.postgresql.org/docs/18/spi.html).

## Bootstrapping single-user mode

To run queries, we need two things:

- An on-disk set of files (the [database cluster](https://www.postgresql.org/docs/current/glossary.html#GLOSSARY-DB-CLUSTER), usually created with `initdb`)
- Some code that interacts with the on-disk data

Creating the database cluster is complex, so for now I'll use `initdb` and come back to this later.

To interact with the on-disk data, we need to initialize various postgres subsystems.

This is the init dance I ended up with. It's probably wrong, but it seems to work. I copied and pasted most of this from different parts of the initialization code, but it was mostly segfault-driven-development.

```c
static int
pg_embedded_init_internal(const char *data_dir, const char *dbname, const char *username) {
	MyProcPid = getpid();
	MyStartTime = time(NULL);
	MemoryContextInit();
	SetDataDir(data_dir);

	InitStandaloneProcess(progname);

	InitializeGUCOptions();

	SelectConfigFiles(NULL, username);

	checkDataDir();
	ChangeToDataDir();

	CreateDataDirLockFile(false);
	LocalProcessControlFile(false);

	process_shared_preload_libraries();

	InitializeMaxBackends();
	InitPostmasterChildSlots();
	InitializeFastPathLocks();
	process_shmem_requests();
	InitializeShmemGUCs();
	InitializeWalConsistencyChecking();

	CreateSharedMemoryAndSemaphores();
	set_max_safe_fds();

	PgStartTime = GetCurrentTimestamp();

	InitProcess();
	BaseInit();
	InitPostgres(dbname, InvalidOid, username, InvalidOid, 0, NULL);

	if (PostmasterContext) {
		MemoryContextDelete(PostmasterContext);
		PostmasterContext = NULL;
	}

	SetProcessingMode(NormalProcessing);

	whereToSendOutput = DestNone;

	// MessageContext is used for query execution and is reset after each query.
	MessageContext = AllocSetContextCreate(TopMemoryContext,
										   "MessageContext",
										   ALLOCSET_DEFAULT_SIZES);


	pg_initialized = true;
	return 0;
}
```

## Running queries

With Postgres' global state more or less matching what the query executor expects, we should be able to run queries via SPI now.

There are _some_ preconditions that I guessed at, either via reading code, reading error messages when lucky or backtraces in GDB when unlucky.

The summarized code for the query executor looks like this

```c
pg_result * pg_embedded_exec(const char *query) {
	pg_result  *result;
	int			ret;

	result = (pg_result *) malloc(sizeof(pg_result));
	memset(result, 0, sizeof(pg_result));

	PG_TRY();
	{
		bool		implicit_tx = false;

		/*
		 * SPI seems to require a TX to be active
		 * If we are running a query without TX, create an implicit
         * TX and auto-commit at the end
		 */
		if (!IsTransactionState())
		{
			StartTransactionCommand();
			implicit_tx = true;
		}

		/*
		 * SPI requires a snapshot to be active.
		 * Push an active snapshot for query execution.
		 */
		PushActiveSnapshot(GetTransactionSnapshot());

		/* Create a new SPI connection
         * There are some memory lifetimes tied to the connection
         * so if we keep reusing the same connection, memory use grows
         */

        SPI_connect();

		ret = SPI_execute(query, false, 0);		/* false = read-write, 0 = no
												 * row limit */

		result->status = ret;
		result->rows = SPI_processed;
		result->cols = 0;
		result->values = NULL;
		result->colnames = NULL;

		// Copy data for queries with results (SELECT or RETURNING)
		if (ret > 0 && SPI_tuptable != NULL) {
			SPITupleTable *tuptable = SPI_tuptable;
            // Lifetime of SPI_tuptable is tied to the SPI connection
            // copy_tuptable uses `malloc()` to decouple lifetimes
            copy_tuptable(SPI_tuptable, result);
		}

		SPI_finish();
		PopActiveSnapshot();

		if (implicit_tx)
			CommitTransactionCommand();
	}
	PG_CATCH();
	{
		ErrorData  *edata;

		/* Get error data and copy message before aborting */
		edata = CopyErrorData();
		FlushErrorState();

		snprintf(pg_error_msg, sizeof(pg_error_msg),
				 "Query failed: %s", edata->message);

		AbortCurrentTransaction();
		result->status = -1;
		return result;
	}
	PG_END_TRY();

	return result;
}
```

## Executing non-queries

I implemented transactions, which are just trivial wrappers for `StartTransactionCommand`/`CommitTransactionCommand`/`AbortCurrentTransaction` with some error handling.

I didn't implement `prepare` or `execute_plan`. Maybe next time.

## Using the library

Having a static library, it's trivial to use it from some C code:

```c
pg_embedded_init(datadir, "postgres", "postgres");
result = pg_embedded_exec("SELECT version()");
if (result && result->status < 0) {
	fprintf(stderr, "ERROR: %s\n", pg_embedded_error_message());
}
print_result(result);
pg_embedded_free_result(result);
```

and we can compile it with
```bash
musl-gcc -static \
    -I "$POSTGRES_ROOT/src/include" \
    -I "$POSTGRES_ROOT/src/backend/embedded" \
    test_embedded.c \
    "$STATIC_LIB" \
    -o test_embedded
```

but there are a few undefined symbols when linking:

```text
src/backend/tcop/postgres.c:3864:(.text.process_postgres_switches+0x106): undefined reference to `parse_dispatch_option'
/usr/bin/ld: src/backend/tcop/postgres.c:4031:(.text.process_postgres_switches+0x6be): undefined reference to `progname'
/usr/bin/ld: src/backend/tcop/postgres.c:4036:(.text.process_postgres_switches+0x731): undefined reference to `progname'
/usr/bin/ld: src/backend/tcop/postgres.c:4036:(.text.process_postgres_switches+0x74f): undefined reference to `progname'
collect2: error: ld returned 1 exit status
```

these symbols are dead code, but it's a symptom of my hacky approach of `#include`ing `.c` files.

It's OK, we can make stubs:
```c
const char *progname = "postgres_embedded";
int optreset = 0;
DispatchOption parse_dispatch_option(const char *name) {
    return 0;
}
```

with which the `test_embedded` will build:
```bash
$ musl-gcc -static -o test_embedded ...
$ file test_embedded
test_embedded: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), statically linked, stripped
$ ldd test_embedded
        not a dynamic executable
```

and when run, it prints:

```text
$ ./test_embedded
Status: 5, Rows: 1, Cols: 1

Column names:
  [0] version

Data:
  Row 0: PostgreSQL 19devel on x86_64-pc-linux-musl, compiled by x86_64-linux-gnu-gcc (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0, 64-bit
```

So far so good, but will this work when called from other languages? Are there any sneaky libc/stdlib dependencies?

## Creating bindings

We can generate Rust bindings very easily with `bindgen` (pointing to the pre-built static file):

```rust
println!("cargo:rustc-link-search=native={}", postgres_dir);
println!("cargo:rustc-link-lib=static=postgres");

println!("cargo:rerun-if-changed={}/libpostgres.a", postgres_dir);
println!(
    "cargo:rerun-if-changed={}/src/backend/embedded/pgembedded.h",
    postgres_dir
);

let bindings = bindgen::Builder::default()
    .header(format!(
        "{}/src/backend/embedded/pgembedded.h",
        postgres_dir
    ))
    .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
    .wrap_unsafe_ops(true)
    .generate()
    .expect("Unable to generate bindings");

let out_path = PathBuf::from(env::var("OUT_DIR").unwrap());
bindings
    .write_to_file(out_path.join("bindings.rs"))
    .expect("Couldn't write bindings!");
```

and it just works
```bash
$ cargo build --release --target x86_64-unknown-linux-musl
$ ldd ./target/x86_64-unknown-linux-musl/release/safe_example
        statically linked
$ ls -lh ./target/x86_64-unknown-linux-musl/release/safe_example
12M ./target/x86_64-unknown-linux-musl/release/safe_example
```

Did I mention that I love `bindgen`?

## Adding some thin wrappers for the bindings

The bindings prove that things work, but if you write this Rust code

```rust
let query = CString::new("SELECT version()").unwrap();
let result = pg_embedded_exec(query.as_ptr());
if !result.is_null() && (*result).status < 0 {
    eprintln!("ERROR: {}", get_error_message());
}
print_result(result);
pg_embedded_free_result(result);
```

you may as well write C.

I wrote a thin wrapper around the generated bindings, and it looks much more like what I'd expect
```rust
let db = Database::connect(datadir, "postgres", "postgres")?;

let result = db.execute("SELECT version()")?;
for row in result.rows() {
    if let Some(version) = row.get(0) {
        println!("Version: {}\n", version);
    }
}
```

It's still not very idiomatic, but it shows promise that it _could_ be.

Given how I wrote the C "API", results force unnecessary allocation to avoid dealing with data lifetimes, but this could be fixed with some brain power.


## Creating a db cluster on disk

While this library works, it requires an existing [database cluster](https://www.postgresql.org/docs/current/glossary.html#GLOSSARY-DB-CLUSTER)—a set of files on disk. The classic way you get a database cluster is by running `initdb`.

Up to this point, I'd probably spent around 6 hours messing with postgres, and thought surely, _surely_, writing an empty cluster to disk can't be _that_ hard.

I was pretty wrong. I spent the next ~16 hours trying to make this work and got _kind_ of a database on disk, but I've not yet made it work.

My current database passes some checks, but then bails on

```text
FATAL:  pre-existing shared memory block (key 35794584, ID 1605763) is still in use
```

because I am not cleaning up some unknown global state between mode transitions.

Why is this so hard? I think that Postgres global state is the answer. There are a few different 'modes' in which the postgres binary can run, and they modify this state.

During this process, I learned a few things that I considered a bit cursed, and you get to learn about them as well!

### Cursed cluster creation

To deal with the differing global state requirements, `initdb` has a "solution": calling `fork` like its life depends on it

```text
$ strace -f initdb ...
execve(["./initdb", ...], []) = 0
[pid 792826] execve(["postgres", "-V"], [] <unfinished ...>
[pid 792828] execve(["postgres", "--check", "-F", "-c", "log_checkpoints=false", "-c", "max_connections=100", "-c", "autovacuum_worker_slots=16", "-c", "shared_buffers=1000", "-c", "dynamic_shared_memory_type=posix"], [] <unfinished ...>
[pid 792830] execve(["postgres", "--check", "-F", "-c", "log_checkpoints=false", "-c", "max_connections=100", "-c", "autovacuum_worker_slots=16", "-c", "shared_buffers=16384", "-c", "dynamic_shared_memory_type=posix"], [] <unfinished ...>
[pid 792832] execve(["postgres", "--boot", "-F", "-c", "log_checkpoints=false", "-X", "1048576", "-k"], [] <unfinished ...>
[pid 792835] execve(["postgres", "--single", "-F", "-O", "-j", "-c", "search_path=pg_catalog", "-c", "exit_on_error=true", "-c", "log_checkpoints=false", "template1"], [] <unfinished ...>
[pid 792838] execve("/usr/bin/locale", ["locale", "-a"], [] <unfinished ...>
```

so, it calls `postgres -V` to check versions match with itself, then it starts postgres 4 separate times, to operate on the files on disk

- in `check` mode, with 1k shared buffers
- in `check` mode, with 16k shared buffers
- in `boot` mode
- in `single` mode


### Cursed cluster bootstrap

Within the cluster bootstrapping process, I found out that there's a catalog file (`postgres.bki`, 12K lines) that defines tables, indices, etc. This catalog file is parsed line by line, gets some tokens replaced, then is interpreted.

Why is it this way? If the `bki` file is tied to the postgres version, _surely_ this could be handled during the build process?

In the follow-up stages of the bootstrap process, I found out that the `plpgsql` extension is _mandatory_—if an extension is mandatory, why is it an extension? Shouldn't it be part of postgres?

After this bootstrap, more of the initial template needs to be populated, and it's done via these SQL files:

 - src/include/catalog/system\_constraints.sql
 - src/backend/catalog/system\_functions.sql
 - src/backend/catalog/system\_views.sql
 - src/backend/catalog/information\_schema.sql

I haven't convinced myself whether using SQL to bootstrap the database is cursed or genius, so I'll let it slide. However, requiring these files on the host filesystem is definitely crazy.
Users are not expected to modify them, and it's an internal bringup detail. Why are they not bundled in the binary?

## Benchmarks

I ran two benchmarks from [pglite's list](https://pglite.dev/benchmarks), both on postgres-lib and on sqlite.

For the "durable" settings, I set:
- Postgres: `{ fsync: true, synchronous_commit: true, full_page_writes: true }`
- sqlite: `PRAGMA synchronous = ON`

and for "non-durable" I set them all to false/off.

Because it was easier to write, I wrote the Postgres benchmark in Rust, using the 'idiomatic' bindings.

|Benchmark|DB|durable|non durable|
|---------|--|--------|----------|
|Insert 1k rows       |Sqlite  |1158ms|4ms|
|Insert 1k rows       |Postgres|240ms|10ms|
|Insert 25k rows in TX|Sqlite  |56ms|3ms|
|Insert 25k rows in TX|Postgres|158ms|149ms|


Postgres seems... slower than I expected. I used `strace` to see if there was anything obvious and found that _every_ query emits an `madvise(MADV_FREE)` syscall.

To validate these numbers, I re-wrote the Postgres benchmark in C (with musl), and the syscall-per-query disappeared; I assume it's related to the extra allocations that I'm doing to cross the FFI boundary.


|Benchmark|DB|Method|durable|non durable|
|---------|----|--|--------|----------|
|Insert 1k rows       |Sqlite  |CLI          |1158ms|4ms|
|Insert 1k rows       |Postgres|Rust bindings|240ms|10ms|
|Insert 1k rows       |Postgres|C bindings   |235ms|9ms|
|Insert 25k rows in TX|Sqlite  |CLI          |56ms|3ms|
|Insert 25k rows in TX|Postgres|Rust bindings|158ms|149ms|
|Insert 25k rows in TX|Postgres|C bindings   |130ms|130ms|


Compared to the numbers I got on [pglite's web benchmark](https://pglite.dev/benchmarks), the **non**-durable versions of these benchmarks are about 3x faster. Keep in mind that this compares completely different environments (browser WASM vs native program).

## Wrapping up

While writing this post, I wanted to check whether there was a hidden `fork` inside my library, making all of this moot; so I ran the test binary under strace.

- Good news: no `fork()`
- Bad news: I found 1000 `dup(2)` calls, followed by 1000 `close(fd)` calls.

Turns out that `count_usable_fds` checks how many FDs it's able to open by.. opening as many as it can. Sure, it's defensive programming. It's also dumb that this is necessary.

## Summary

It's possible to build postgres statically, and with the use of some careful wrappers, use postgres as a library. Bindings for different languages are easy to build, but managing lifetimes in an idiomatic way is more complex.

There are downsides to the current proof of concept, but it's possible to fix them with more work:
- `initdb` does not work—use the `initdb` binary or ship a bundled tarball with an empty cluster
- Unloading the db poisons the global state—need to implement re-initialization
- There's dead code in the final artifact—due to importing `.c` files

Some features are not implemented:
- Loading of dynamic extensions
- Prepared statements

There is a fundamental limitation with this approach: the library is single-threaded only, so you can't execute concurrent queries.

---
title: Postgres server as a library
date: 2025-12-08
tags: postgres, no-effort
slug: postgres-library
description: global state was a mistake
---

I feel like I just woke up from a fever dream, I've spent a large chunk of the last 72 hours reading the Postgres codebase.

Why would you do that to yourself, you may ask. Well, I recently found out about [pglite](https://pglite.dev/), a project to build Postgres as a WASM(+WASI) blob
and use it as a library.

The thing is, I am weirdly driven by cursed projects and spite.

My love of cursedness had made me into a WASM fan (LEB128 in an ISA? what could be more cursed than that!), but sometimes there's such a thing as too cursed, even for me. When they implemented variable-length-instructions for a _virtual ISA_, I joined the WASM-haters-club.

I have a much longer, much more concrete WASM rant in me, but it'll require some effort to write down, so now is not the time.

Back to Postgres and pglite -- if they can build it in WASM, then _surely_ it is possible to build Postgres as a regular library (shared/static) and use it. I know nothing about postgres internals, but jumping in feet first has never gone wrong before.

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

This gives a ~100MB static file with 875 object files inside, _probably_ a lot of them are unused, but that's ok.

## Analyzing Postgres startup

Postgres is usually compiled to a binary (`postgres`) which runs as a server and dispatches incoming connections into some kind of internal event loop, which performs some IO and calculations, and gives an answer back.

_Surely_ it should possible to bypass the whole server/connection dance and just execute the query code directly.

Around here is where about 16 hours of my weekend disappeared. What I thought would be "just call some function" became "read through all paths of postgres initialization behavior and see how it affects global state".

Why? Because even though postgres is one of the pieces of technology keeping the world together, its started as a university project 30~35 years ago, and it shows. There is _significant_ global state, seemingly everything I touched wanted to read or write from it.

I assume that because a bunch of state is global, the architecture of Postgres relies on `fork()` to execute parts of code that need to temporarily modify the global state.



It turns out that postgres has [single user mode](https://www.postgresql.org/docs/current/app-postgres.html#APP-POSTGRES-SINGLE-USER) which does exactly this, all we need to do is somehow call this code directly.

The plan is to emulate single-user mode by performing some amount of setup, then querying the DB directly via the [Server Programming Interface](https://www.postgresql.org/docs/8.1/spi.html)

## Initializing Postgres

This is the init dance I ended up with. It's probably wrong, but it seems to work. I copied and pasted all of this from different parts of the initialization code, but it was mostly segfault-driven-development.

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

	/*
	 * Perform an empty transaction to finalize SPI setup.
	 * This ensures the system is ready for query execution.
	 */
	StartTransactionCommand();
	if (SPI_connect() != SPI_OK_CONNECT)
	{
		snprintf(pg_error_msg, sizeof(pg_error_msg), "SPI_connect failed");
		AbortCurrentTransaction();
		return -1;
	}
	SPI_finish();
	CommitTransactionCommand();

	pg_initialized = true;
	return 0;
}
```

TODO: shared plpgsql lib

## Running queries

With Postgres' global state more or less matching what the query executor expects, we should be able to run queries via SPI now.

There are _some_ preconditions that I mostly guessed at, either via reading code, reading error messages when lucky or backtraces in GDB when unlucky.

The summarized code for the query executor looks like this (you don't get to shame my memory allocation "strategy" at this point in time)

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
            // so we need to copy it
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

I did trivially implement transactions but that's just error-handling that wraps `StartTransactionCommand`/`CommitTransactionCommand`/`AbortCurrentTransaction`.

I didn't implement `prepare` or `execute_plan`. Maybe next time.

## Using the library

Having a static library, it's trivial very use to call from some C code:

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

these symbols are dead code, but I just hacked a bunch of stuff and `#include`d `.c` files, so the symbols are required.

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


## Creating bindings

So far so good, but will this work when called from other languages? Are there any sneaky libc/stdlib dependencies?

We can try it out very easily with rust+bindgen (pointing to the pre-built static file), but it's not happy:

```text
error: linking with `cc` failed: exit status: 1
  |
  = note:  "cc" "-m64" "/tmp/rustciM53nE/symbols.o" ... "-nodefaultlibs"
  = note: some arguments are omitted. use `--verbose` to show all linker arguments
  = note: rust-lld: error: undefined symbol: sigsetjmp
          >>> referenced by pgembedded.c:100 (src/backend/embedded/pgembedded.c:100)
          >>>               pgembedded.o:(pg_embedded_init_internal) in archive target/debug/deps/libtest_pgemb-b6c92dbb1b302a71.rlib
          >>> referenced by pgembedded.c:416 (src/backend/embedded/pgembedded.c:416)
          >>>               pgembedded.o:(pg_embedded_exec) in archive target/debug/deps/libtest_pgemb-b6c92dbb1b302a71.rlib
          >>> referenced by pgembedded.c:592 (src/backend/embedded/pgembedded.c:592)
          >>>               pgembedded.o:(pg_embedded_begin) in archive target/debug/deps/libtest_pgemb-b6c92dbb1b302a71.rlib
          >>> referenced 48 more times
          collect2: error: ld returned 1 exit status
```

so here `-nodefaultlibs` means that we don't have `sigsetjmp` which is provided by the stdlib, but we can stub it out
```c
int sigsetjmp(sigjmp_buf env, int savemask) {
    (void) savemask;
    return setjmp(env);
}
```

```bash
$ cargo build --release --target x86_64-unknown-linux-musl
$ ldd ./target/x86_64-unknown-linux-musl/release/safe_example
        statically linked
$ $ ls -lh ./target/x86_64-unknown-linux-musl/release/safe_example
12M ./target/x86_64-unknown-linux-musl/release/safe_example
```

## Adding some thin wrappers for the bindings

The bindings prove that things work, but if you write this rust code

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

obviously this is not very idiomatic, and this API forces allocations, which could be avoided with some brain power.


## Creating a db cluster on disk

While this library works, it requires an existing "cluster" -- a set of files on disk. The classic way you get a database cluster is by running `initdb`.

Up to this point, I'd probably spent around 6 hours messing with postgres, and thought surely, _surely_, writing an empty cluster to disk can't be _that_ hard.

I was pretty wrong. I spent the next ~12 hours trying to make this work and got _kind_ of a database on disk, but I've not yet made it work.

My current database passes some checks, but then bails on 

```text
FATAL:  pre-existing shared memory block (key 35794584, ID 1605763) is still in use
```

so some more work is needed.

Why is this so hard? I think that Postgres global state is the answer. There are a few different 'modes' in which the postgres binary can run, and they modify this state.

During this process, I learned a few things that I considered a bit cursed, and you get to learn about them as well!

### Cursed cluster creation

To deal with the differing global state requirements, `initdb` has a "solution": calling `fork` like its life depends on it

```text
execve(["./initdb", "-L", "asd", "pgdata4", "--wal-segsize=1", "--locale=C", "--encoding=UTF-8", "--no-sync", "--no-instructions", "--auth-local=trust"], []) = 0
[pid 792826] execve(["postgres", "-V"], [] <unfinished ...>
[pid 792828] execve(["postgres", "--check", "-F", "-c", "log_checkpoints=false", "-c", "max_connections=100", "-c", "autovacuum_worker_slots=16", "-c", "shared_buffers=1000", "-c", "dynamic_shared_memory_type=posix"], [] <unfinished ...>
[pid 792830] execve(["postgres", "--check", "-F", "-c", "log_checkpoints=false", "-c", "max_connections=100", "-c", "autovacuum_worker_slots=16", "-c", "shared_buffers=16384", "-c", "dynamic_shared_memory_type=posix"], [] <unfinished ...>
[pid 792832] execve(["postgres", "--boot", "-F", "-c", "log_checkpoints=false", "-X", "1048576", "-k"], [] <unfinished ...>
[pid 792835] execve(["postgres", "--single", "-F", "-O", "-j", "-c", "search_path=pg_catalog", "-c", "exit_on_error=true", "-c", "log_checkpoints=false", "template1"], [] <unfinished ...>
[pid 792838] execve("/usr/bin/locale", ["locale", "-a"], [] <unfinished ...>
```

so, it calls `postgres -V` to check versions match with itself, then it starts postgres 4 separate times, to operate on the files on disk

- in `check` mode
- in `check` mode
- in `boot` mode
- in `single` mode


### Cursed cluster bootstrap

Within the cluster bootstrapping process, I found some interesting stuff.

There's a catalog file (`postgres.bki`, 12K lines) that defines tables, indices, etc. This catalog file is parsed line by line, gets some tokens replaced, then is interpreted.

Why is it this way? if the `bki` file is tied to the postgres version, _surely_ this could be handled during the build process?

After this bootstrap, more of the initial template needs to be populated, and it's done via these SQL files:

 - src/include/catalog/system\_constraints.sql
 - src/backend/catalog/system\_functions.sql
 - src/backend/catalog/system\_views.sql
 - src/backend/catalog/information\_schema.sql

I'm not entirely sure if using SQL to bootstrap the database is cursed or genius, so I'll let it slide. However, what I'm sure about is that requiring these files to be present on the host filesystem is crazy. Users are not expected to modify them, 
and it's an internal bringup detail. Why are they not bundled in the binary?

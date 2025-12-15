---
date: 2025-12-15
incomplete: true
tags: postgres
title: Postgres lib 2
description: electric boogaloo
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

CREATE FUNCTION hello_world() RETURNS text AS 'example', 'hello_world'
LANGUAGE C STRICT IMMUTABLE;
```

If we are building all of Postgres as a static lib, it makes little sense to build extensions as dynamic libraries (ignoring the fact that without a dynamic loader, manually loading a shared library is a pain in the ass), so, the only sane option is to build extensions as static libraries, along with Postgres.

If we take a very simple extension:
```c
#include "postgres.h"

PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(add_one);

Datum add_one(PG_FUNCTION_ARGS) {
	int32 arg = PG_GETARG_INT32(0);
	PG_RETURN_INT32(arg + 1);
}
void _PG_init(void) {
	elog(NOTICE, "Example static extension initialized");
}
```
Building it is trivial (`musl-gcc -static -I../src -o example.a`), but how to plug it into Postgres?

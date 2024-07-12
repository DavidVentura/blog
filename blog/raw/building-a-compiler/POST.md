---
title: Pico8 console, part 3: Writing a compiler & Lua runtime
date: 2023-09-03
tags: c, lua, pico8, picopico
slug: picopico-compiler-runtime
description: 
series: picopico
series_idx: 3
---

In [part 2](https://blog.davidv.dev/pico8-console-part-2-performance.html) I was stuck trying to make `Rockets!` work with optimized bytecode; I pursued this for a bit and realized it was probably never going to be fast enough.


So I set out to write a compiler.

It was a dumb idea, but it worked.


For a proof of concept, I started writing the compiler in C++. I do not really know C++. It was [a terrible idea](https://github.com/DavidVentura/lua-but-worse/blob/7b232ffe9a124c56af5fefccdd4fba6de917cd05/test_cases/metatable/out.cpp).

I got something kinda working, but the parser had the completely wrong abstraction, and the generated C++ was also terribly dumb.

After a while, I decided to ditch that, re-write the parser and output plain C11; the current state of the compiler works for _most_ cases, though there are still some bugs.

A very basic compiler can be thought of as 3 parts:

* Parser: read source code and generate an abstract syntax tree
* Intermediate representation: Convert the source AST into an AST that is more amenable for the target output
* Code emitter: generates concrete representation from the AST

## Dealing with types

Lua is a dynamically typed language, with only 6 types:

- Number
- Nil
- Table
- String
- Boolean
- Function

and it allows certain operations to span distinct types:

```lua
a = 1
b = "hi"
print(a..b) -- ".." is the concatenation operator
```

As C is a statically typed language, the type of each argument must be defined in advance.
Writing/generating functions in C that can take any combination of types would be a tremendous pain, so 
the way that I'm dealing with this is by using [sum types (a tagged union)](https://en.wikipedia.org/wiki/Tagged_union).

```c
typedef struct TValue_s {
	union {
		uint16_t str_idx;
		fix32_t num;
		uint16_t table_idx;
		Func_t fun;
	};
	enum typetag_t tag;
} TValue_t;
```

and I'm defining the `typetag_t` type to match the necessary types:
```c
enum typetag_t {NUL=0, STR=1, TAB=2, FUN=3, NUM=4, BOOL=5};
```

Given that now all types are representable by "one type" on their C representation, the type system will happily let us "mix types", as they are just `TValue_t`s.

```c
function concat(TValue_t a, TValue_t b) {
/* You can imagine something like
 * if (a.tag == NUM) {
 * ...
 * }
 */
}
```

## First-Class Functions

Lua allows you to do many things that are not really possible to express in C: anonymous functions, closures, optional arguments, etc.

As an example, an anonymous function can be assigned to a variable:

```lua
a = function()
...
end
```

These semantics have to be transformed into something that's possible to express in C, so in this case we could replace the anonymous function with a named function

```c
function __anonymous_function_a() {
...
}
```
and assigning a TValue wrapper to the local variable

```c
a = TFUN(__anonymous_function_a);
```

Apart from having anonymous functions, all arguments that a function declares in its signature are optional:
```lua
function f(a,b,c,d)
  print(a)
end
f()
```

Any value that's not passed in, will be `nil`.

On top of _that_, you can also pass extra arguments to functions:
```lua
function f()
end
f(1,2,3,4)
```

To deal with this, I decided on the following calling convention:

All functions receive a single argument of type `TVSlice_t` (a slice being an array of `TValue` + an explicit `length` field).

You can imagine that all calls end up looking like

```c
void f(TVSlice_t arguments) {
// ...
}

f({.elems=NULL, length=0}); 			// equivalent to f()
f({.elems=(TValue_t[]){1}, length=1}); 	// equivalent to f(1)
```

And to deal with the possibility of missing arguments, the function itself is rewritten as
```c
// Equivalent of function f(a,b,c,d) .. end
void f(TVSlice_t arguments) {
    TValue_t a = __get_arg(arguments, 0);
    TValue_t b = __get_arg(arguments, 1);
    TValue_t c = __get_arg(arguments, 2);
    TValue_t d = __get_arg(arguments, 3);
}
```

where `__get_arg` will return `nil` if there were not enough arguments passed in.

### Closures

Lua's functions are allowed to enclose values from their context/scope, even after the context has exited.

In the most basic case:
```lua
local captured = 7
a = function()
  return captured
end
a()
```

we "capture" values that are defined _outside_ the function itself.  This is mildly problematic, as there's nothing similar to this in C.

What I did is to transform all closures into "regular" functions in a few steps:

First, make the captured arguments an explicit table
```lua
local captured = 7
a = function(captured_args)
  return captured_args.captured
end
a()
```

This obviously fails, the argument is now explicit and we are not passing it in, so in the following AST transformation pass, we pass all the necessary captured arguments in a temporary table:

```lua
local captured = 7
a = function(captured_args)
  return captured_args.captured
end
_env_for_a = {captured=captured}
a(_env_for_a)
```

This representation is fairly trivial, but it took me quite a bit to understand the scoping rules of what gets captured, how and when.

When a variable (`captured`) is not defined in local scope, walk the scopes upwards, looking for the `captured` node as either:
  - a `LocalAssign` AST node (`local captured`)
  - a function's `Argument` (`function f(captured) ... end`)
  - an `Assign` node in the global scope (`captured = 7`)

If we combine this with standard function arguments, a secret, extra argument named `lambda_args` is added:

```lua
local captured = 7
a = function(some_arg)
  return captured*some_arg
end
a(5)
```

becomes

```c
TValue_t captured = 7;

void a(TVSlice_t arguments) {
  TValue_t some_arg    = __get_arg(arguments, 0);
  TValue_t lambda_args = __get_arg(arguments, 1);
  TValue_t captured    = get_tabvalue(lambda_args, "captured");
  // equivalent of `lambda_args.captured`

  return some_arg * captured;
}

TValue_t lambda_args = make_table();
set_tabvalue(lambda_args, "captured", captured);
a((TVSlice_t){.elems=(TValue_t[]){5, lambda_args}, length=2});
// equivalent of a(5, {captured=captured})
```

## Implementing Lua

With the compiler in this state, code can be transformed to syntactically correct C, but the expected behavior is not yet implemented. 

### Runtime

I opted to manage memory with three arenas:

- Tables
- Strings
- Closures

Doing it this way, the arenas are as compact as possible and there's no need to check for union discriminators on any operation.

Keeping each complex type in an arena (a big array) also allows for:

- References to be an index into the array (handle/descriptor), which saves 2 bytes when compared to using a pointer (on a 32bit platform)
	- In turn, this allows `realloc`ing the entire array onto another base address, while keeping all references valid
- Re-using the same objects over and over instead of freeing and re-allocating
- The comparison operator for complex values to be reduced to comparing the indexes

The 'value' type is then:

```c
typedef struct TValue_s {
	union {
		uint16_t str_idx;
		uint16_t table_idx;
		uint16_t fun_idx;
		fix32_t num;
	};
	enum typetag_t tag;
} TValue_t;
```

which is 5 bytes.

### Tables

Tables store key-value pairs, both key and values can be of any type (number, string, function, table)

They can be defined as:
```c
typedef struct Table_s {
	Metamethod_t* mm;
	KVSlice_t kvp;
	uint16_t metatable_idx;
	uint8_t refcount;
} Table_t;

typedef struct Metamethod_s {
	TValue_t __index;
	TValue_t __add;
	TValue_t __mul;
	TValue_t __sub;
	TValue_t __div;
	TValue_t __unm;
	TValue_t __pow;
	TValue_t __concat;
} Metamethod_t;

typedef struct  KVSlice_s {
	KV_t* kvs;
	uint16_t capacity;
	uint16_t len;
} KVSlice_t;

typedef struct KV_s {
	TValue_t key;
	TValue_t value;
} KV_t;
```

#### Metatables & Metamethods

I chose to implement the metamethods as a dedicated structure instead of using keys on the table, this allows us to skip walking the table in search of the key every time there's an addition/substraction/... operation between tables -- it's very common to assign a table as it's own metatable, and it may require walking tens of keys for each operation.

I've not benchmarked whether this is faster/worth the extra memory usage.

### Closures
As a type, a closure only associates a function (some code) and a table (some data/environment) together.

I chose to use a regular table to store the closure's environment, to it can be defined as:

```c
typedef void (*Func_t)(TVSlice_t, TValue_t*);
typedef struct TFunc_s {
	Func_t fun;
	uint16_t env_table_idx;
} TFunc_t;
```


### Coroutines

I didn't implement them yet, but I had the idea of abusing the closure implementation and adding a `step` parameter, then replacing `yield` points with a `switch` statement; along with probably moving the local variables to the closure state table.

### Memory management

In Lua, memory management is automatic; there's a garbage collector which visits all objects and decides whether they need to be cleaned up. The user of Lua does not have to think about managing memory in any way.

I didn't want to implement a full garbage collector, as I thought that it'd be too complex; Lua handles simple types by value (Number, Boolean, Nil) and complex ones (String, Table) by reference.

Using reference counting for the complex types should be sufficient for _most_ cases, and reference counting is very simple:

* When a reference to A is _stored_, A's internal counter goes _up_
* When a reference to A is _dropped_, A's internal counter goes _down_
* When A's counter reaches zero, A should be destroyed

As an example:

```lua
table = {} -- the anonymous table `{}` is now being referenced by the `table` variable; it's internal counter is now 1.
other_table = table -- now `{}` has a refcount of 2
table = 5 -- `{}` is no longer referenced by table, it's counter is down to 1
other_table = 5 -- `{}` is not referenced anywhere, it can be cleaned up
```

The way that I've implemented this is very straight forward, whenever doing a `set` operation (variable assignment):

1. The source (right-hand-side value) has its counter increased
2. The destination (left-hand-side value), if non-nil, has its counter decreased

This is great! Most of the work is done. The only remaining thing to solve is variables going out of scope:

```lua
function a()
  table = {}
end
-- `{}` is no longer referenced by `table`, as `table` is no longer in scope 
```

C11 provides a way to _automatically_ execute a function whenever a variable goes out of scope, the `cleanup` attribute. This attribute is placed _on_ the variable, and references a function to run:

```c
void decref(TValue_t* ptr) {
  // *ptr is going out of scope, do something with it, like
  ptr->refcount--;
  if (ptr->refcount == 0) free(ptr->data);
}
void main() {
  TValue_t __attribute__((cleanup(decref))) my_var;
}
```

This works out for _most_ scenarios, but not all:

Returning values is problematic:
```lua
function a()
  local var = {field=1}
  return var
end
a()
```

as the reference count of `var` would drop to 0 when the scope finishes, the actual table would be deleted!

To prevent this, we can increase the reference count right before returning the value:
```lua
function a()
  local var = {field=1}
  _incref(var) -- inserted during AST transformation
  return var
end
a()
```

This works, though now we have a new problem, the returned `var` will forever have an extra reference, so it'll never be cleaned up.

The solution is not to just run a bare `_incref`, but to also schedule a `_decref` to balance it out.
The reason to do it this way, instead of scheduling a `_decref` always, is that only a small subset of all variables are returned, adding extra overhead for deferring.
```lua
function a()
  local var = {field=1}
  _mark_for_gc(var)
  return var
end
a()
```
where `_mark_for_gc` just stores the reference to `var`, with which it'll run `_decref` later.

Turns out, I did build a simple GC if this [deferred cleanup](https://bitbashing.io/gc-for-systems-programmers.html) counts!

## Testing

I built a basic testing framework which takes in Lua files, compiles them to C and then runs them, comparing the output on the official Lua interpreter and my version.

This has proven super valuable, both on tests for expected behavior, but also seeing how my changes to the compiler affect the generated code.

## Future

* Benchmarking
* Dynamic loading of the built object, to be able to download games in the console

### Some references

- [Lua AOT 5.4](https://github.com/hugomg/lua-aot-5.4)
- [GCC builtins](https://gcc.gnu.org/onlinedocs/gcc/Other-Builtins.html)

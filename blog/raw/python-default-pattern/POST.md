---
title: Rust's Default in Python
date: 2023-08-18
tags: python, rust, short, TIL
description: Implementing recursive defaults for dataclasses with dacite
---

In Rust, I've used and liked quite a bit the [Default trait](https://rust-unofficial.github.io/patterns/idioms/default.html), which lets you instantiate a struct 
without providing all the members, as a short example:

```rust
#[derive(Debug, Default)]
struct MyStruct {
    value: i32,
}

fn main() {
    let default_struct: MyStruct = Default::default();
    println!("{:?}", default_struct); // Output: MyStruct { value: 0 }
}
```

A very important factor for me, is that this is recursive, as long as all members of each struct implement `Default`.


I had not found a similar thing in Python, but today I learned about [dacite](https://github.com/konradhalas/dacite), which, in combination with dataclasses' `default_factory` can
implement something very similar.


```python
{embed-file example.py}
```

Which outputs

```python
HostData(config=HostConfig(backup=BackupConfig(enabled=False, bucket='default')), cron=[])
HostData(config=HostConfig(backup=BackupConfig(enabled=False, bucket='default')), cron=[Cron(name='do something', command='ls')])
```

This is _very_ different, in my opinion, from adding default values to every property.

By having default values (`enabled: bool = False`) it is possible to perform a partial instantiation, which, for me, is particularly troublesome when parsing user data -- I want the object to be entirely defined, or to entirely fall back to a default; I never want the object to be partially defined.

Default is also something you conciously implement; certain types do not have sane default values, such as `BasicAuth(user, password)` or `Cron`.

By using `Type.default()`, you are being explicit about instantiating a default instance of an object.

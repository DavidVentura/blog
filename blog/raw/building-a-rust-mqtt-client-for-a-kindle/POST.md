---
title: Building an MQTT client for the Kindle
date: 2021-01-07
tags: iot, kindle, rust, cross-compiling
description: The never-ending rabbit hole I found while trying to build a simple MQTT client for the kindle
---
I have a paperwhite kindle on which I run a very dumb python script that broadcasts its' screen events (screen on, off) over the network, it's detailed [here](/integrating-a-kindle-into-house-automation.html).

Recently I read [this post](https://drewdevault.com/2020/10/09/Four-principles-of-software-engineering.html) and its
point about software simplicity made me remember the script that runs in the kindle and all the surrounding machinery that exists for it.

```
              +--> lipc subprocess --> parsing +
python script-|                                +-> udp socket -> udp2mqtt bridge -> mqtt server
     fork     +--> lipc subprocess --> parsing +
```

As an excuse for a side project I picked this topic and set myself goal to make it simpler:

* Should not need to `fork()`
* Should not need to parse results as strings
* Should not need external bridges

and as an arbitrary item, I picked rust as the language to get more familiarity.

# Avoiding fork()

Currently the python script delegates the reception of events to another binary: `lipc-wait-event`
which listens on the [LIPC](https://wiki.mobileread.com/wiki/Kindle_Touch_Hacking#LIPC) bus (the
main IPC bus on the device) and prints lines of text when events match its filters.

By analyzing `lipc-wait-event` with `ldd` we can see that it links to `liblipc.so`. We can do the
same and avoid `fork`ing.

There's not much online about this, but I found the [OpenLIPC headers](https://github.com/Arkq/openlipc)
and converted them with `bindgen`. Super sueful documentation for the functions [is here](https://arkq.github.io/openlipc).

You can also find a [list of known LIPC events](https://www.mobileread.com/forums/showthread.php?t=227859).

Bindgen adds a compiler directive to link with `liblipc` in the bindings.rs file.

## Linking liblipc

Rust can easily link and interop with C libraries -- although here there's a small extra layer of
complexity because the shared library is ARM only, which means we can only link to it using an ARM
cross compiler (or linker in this case?).

I found a [toolchain](https://github.com/samsheff/Amazon-Kindle-Cross-Toolchain/tree/master/arm-kindle-linux-gnueabi)
online and configure it in my `.cargo/config`:

```ini
[target.armv7-unknown-linux-gnueabi]
linker = "Amazon-Kindle-Cross-Toolchain/arm-kindle-linux-gnueabi/bin/arm-kindle-linux-gnueabi-cc"
```

Export the path to sysroot/lib before compiling:
```bash
export SYSROOT_LIB_DIR=~/git/Amazon-Kindle-Cross-Toolchain/arm-kindle-linux-gnueabi/arm-kindle-linux-gnueabi/sysroot/lib/
```

Running `cargo build` at this point fails, as `liblipc` itself can't be found

```bash
rm-kindle-linux-gnueabi/bin/ld: cannot find -llipc
          collect2: ld returned 1 exit status
```

Adding the file to `SYSROOT_LIB_DIR` will be enough to fix this.

A blank program links and runs fine on the kindle. This accomplishes the first item on the
checklist, so let's look into using the exposed functionality.

## Exposing liblipc to the rust environment

A common way to use C libraries in rust is to write an intermediate crate that translates the C
signatures into something that's easier to use from normal rust.

Wrapping unsafe C libs is a big topic, luckily I found [this article](https://medium.com/dwelo-r-d/wrapping-unsafe-c-libraries-in-rust-d75aeb283c65) which helped me delve into it quite a bit.

In this wrapper there are 4 basic functions and the subscribe function.

### Basic functions

Connect: Open a connection to the bus, get a pointer back that will be needed for the other
functions.

Disconnect: Pass the connection pointer to destroy it and free resources.

GetIntProperty: Pass a service string, a property string and an `int*` to get the current value
written to that address. 
An example for service+property strings would be "com.lab126.powerd" "battLevel".

This is pretty straight forward to call, the only special thing here is that the variable `val`
will be modified in-place by liblipc.

```rust
pub fn get_int_prop(&self, service: &str, prop: &str) -> Result<i32, String> {
    let mut val: c_int = 0; // value will be written here by LipcGetIntProperty
    let service = CString::new(service).unwrap();
    let prop = CString::new(prop).unwrap();
    let ret_code;
    unsafe {
        ret_code = LipcGetIntProperty(
            self.conn,
            service.as_ptr(),
            prop.as_ptr(),
            &mut val
        );
    };
    if ret_code == LIPCcode_LIPC_OK {
        Ok(val)
    } else {
        Err(format!("Error getting property! {:?}", ret_code))
    }
}

```

This runs great and returns decent values for successes and errors:
```
r.get_int_prop("com.lab126.powerd", "battLevel");
60
r.get_int_prop("com.lab126.powerd", "battTemperature");
Error getting property! 8
```

GetStringProperty: Pass a service, a filter property and a `char**` to get the current value
written to that address. This is exactly the same as `get_int_prop` but we pass a string handle (handle\_ptr):
```rust
let mut handle: *mut c_char = std::ptr::null_mut();
let handle_ptr: *mut *mut c_char = &mut handle;
```

For both GetStringProperty and GetIntProperty, it'd be nice to not have to deal with all the
shenanigans related to return-code handling and return a readable error, instead of its integer value.

For the readable error, luckily liblipc provides a function we can call for this: `LipcGetErrorString`.
The code to return a `String` from rust is pretty trivial:

```rust
fn code_to_string(code: u32) -> String {
    unsafe {
        let cstr = CStr::from_ptr(LipcGetErrorString(code));
        return String::from(cstr.to_str().unwrap());
    }
}
```

With this, we can change our `format!`ted string above to contain the error message:
```rust
Err(format!("Error getting property! {:?}", code_to_string(ret_code)))
```

Which works nicely with a tiny example program:
```rust
let r = rLIPC::new().unwrap();
let batt_t = r.get_int_prop("com.lab126.powerd", "battTemperature")?;
```

```bash
$ ./libopenlipc-sys
Failed to subscribe: lipcErrNoSuchProperty
```

Great!

Now, it'd also be great if I could also stop copy-pasting the whole "compare result to OK and
return a nice string if it's different", so I looked up how to write macros for rust which, for the
simple macro I wanted, is quite easy.

A macro is essentially a way to copy-paste code automatically (or, better said, the macro expands
to the same code, replacing place-holder tokens with concrete values).

My trivial macro looks like this:

```rust
macro_rules! code_to_result {
    ($value:expr) => {
        if $value == LIPCcode_LIPC_OK {
            Ok(())
        } else {
            Err(format!(
                "Failed to subscribe: {}",
                rLIPC::code_to_string($value)
            ))
        }
    };
}
```

(Which now that I look at it, has no advantage over a regular function, but oh well).

### Subscribe function

For `SubscribeExt` you also pass a service and a filter property, but along with them you send:

* A nullable pointer to a (callback) function that takes `char* name, Event* event, void* data` as arguments.
* A nullable pointer to anything, this is what `void* data` is on the previous line -- it's a way
  to send some context from the function that registers the callback to the called function.


This was quite tricky to get working without fully understanding, luckily `@pie_flavor` in the rust
discord helped me a lot.

#### Hitting an invisible wall

The first issue that took me a *long* while to understand, was that the compiler will not alert you
about scoping when dealing with pointers.  
Looking at this code you can see it's sliiiiiightly different than before -- we are calling 
`.as_ptr()` and storing that, instead of storing the CString.

Guess what, the CString is out of scope because we don't use it anymore!

```
let _service = CString::new(service).unwrap().as_ptr();
                                             ^
                  CString goes out of scope here
		  _service now is a dangling pointer :)
```

In regular rust, `_service` would hold a reference to the CString, which would make it not go out
of scope immediately -- with pointers this is not the case. There is a [big fat warning](https://doc.rust-lang.org/std/ffi/struct.CString.html#method.as_ptr)
on the docs, which I managed to glance over.

#### Hitting a regular wall

I am sending a regular function pointer to liblipc that will be called back when an event triggers,
but what I really want is to call arbitrary rust functions, not this very-specific, very-ugly function
that implements the required signature.

In regular code, I'd use a closure and call a function from the outer scope from within the
closure, something like

```rust
LipcSubscribeExt(..., |...| { callback_from_outer_scope(..) });
```

However, [a closure is not a function](https://doc.rust-lang.org/book/ch19-05-advanced-functions-and-closures.html),
 which means we can't just call a closure!

The way people deal with this in C is by providing an opaque pointer (void\* data) to the function that will call
you back, the function will then pass the opaque pointer (void\* data) to you when executing the callback, in pseudocode:

```c
fn_that_calls_back(to_call_back, *data);
..
void to_call_back(.., *data) {
// Do whatever with data, probably something like (*data)(args);
}
```

I was stuck with this and asked for help on the rust discord, where @pie\_flavor said

> The callback can't be passed directly - we have double box it; once to safely transport the type
> data and once again to have a fixed-size object to reference.

I'm not sure I fully understand this -- I haven't really had enough experience to grok it.
The [docs](https://rust-lang.github.io/unsafe-code-guidelines/layout/function-pointers.html#use)
 don't really mention this either.

The end result looks like this:

Register the callback
```rust
let boxed_fn: Box<dyn FnMut(&str, &str, Option<i32>, Option<String>) + Send> =
    Box::new(callback) as _;
let double_box = Box::new(boxed_fn);
let ptr = Box::into_raw(double_box);
LipcSubscribeExt(
                ...,
                ...,
                ...,
                Some(ugly_callback),
                ptr as *mut c_void,
            );
```

And the function that will be called back

```rust
unsafe extern "C" fn ugly_callback(
    _: *mut LIPC,
    name: *const c_char,
    event: *mut LIPCevent,
    data: *mut c_void,
) -> LIPCcode {
    ...
    let f = data as *mut Box<dyn FnMut(&str, &str, Option<i32>, Option<String>) + Send>;
    (*f)(_source, _name, _int_param, _str_param);
}
```

With this, we get callbacks to rust with proper typed data, there's no need to parse strings to get
back the values.

You can find the crude crate [here](https://github.com/DavidVentura/kindle-events-parser/tree/master/libopenlipc-sys).

This accomplishes the second item in the checklist.

# Publishing events without requiring an external bridge

With a rust callback registered for the events we are interested in, the only thing left to do is
to publish them on MQTT.

I tried both wrappers around libmosquitto and pure rust clients, but they either failed to build
with the toolchain or failed during runtime as they required a newer glibc version.

I remembered having seen a [single file](https://github.com/micropython/micropython-lib/blob/master/umqtt.simple/umqtt/simple.py)
 python implementation (and it is in fact what I run on my microcontrollers), so I thought I could
 translate it to rust and use that, without any dependencies it should work.

## Writing a basic MQTT publisher

You can find my literal translation of umqtt.simple [here](https://github.com/DavidVentura/kindle-events-parser/tree/master/mqtt-simple)
 -- it's not complete as it only suports AtMostOnce publishing but it does what I need and it
 offers a oneshot publish function (that is connect, publish, disconnect).

It was a bit tricky to translate as initially I did not realize some bytes of the buffers were
being reused - so I had some extra bytes in there, but when comparing what my `publish` message looked
like in wireshark to one generated with `mosquitto_pub` the differences became plain to see.

This worked fine when connecting to an IP address, but failed to compile when trying to resolve
names, complaining about being unable to link:

```
  = note: arm-kindle-linux-gnueabi/sysroot/usr/lib/libdl.a(dlsym.o): In function `dlsym':
          dlsym.c:(.text+0xc): undefined reference to `__dlsym'
          collect2: ld returned 1 exit status
```

I spent hours fiddling with `RUSTFLAGS` but nothing changed. I asked a few times on the rust
discord but none of the proposed solutions worked for me. An interesting one was to use a DNS
client written completely in rust, I didn't want to follow that on principle, DNS works on the
kindle, it's definitely a "bug" in how the binary is linked by rust or by the linker.

I took a shot in the dark and decided to try building a new toolchain. I wasn't sure it was going
to do anything, but it might be better than a random tar downloaded from 2013 from the mobilereads
forum.

### Building a new toolchain

Building a new cross-compiler toolchain with crosstool-ng was super easy, I followed the
instructions on the official docs which boil down to:

```bash
$ ct-ng arm-unknown-linux-gnueabi
$ ct-ng menuconfig
```

on the menu, I:

* picked libc=2.12.1 
* picked kernel 2.6.32
* set vendor prefix to `kindle`
* turned `CT_DEBUG_CT_SAVE_STEPS` on (so you can rebuild if it fails)
* disabled `gdb` after a failure building
  * there's a patch [here](https://github.com/crosstool-ng/crosstool-ng/issues/1249) but I don't need gdb anyway.

then `ct-ng build` gave me a cross-compiler toolchain that you can find
[here](/files/kindle-toolchain.tar.gz) (71MB).


## Re-adding DNS support

With the new toolchain, DNS worked fine, but I'm not sure why.
This accomplishes the last item in the checklist.

With working DNS, I could try going back to rumqttc for MQTT, but it pulls like 50 dependencies and
I'm not sure it's worth it. `mqtt-simple` has been working fine.

A simplified snippet of the result looks like this:

```rust
use libopenlipc_sys::rLIPC;
use mqtt_simple::publish_once;
fn main() {
    let r = rLIPC::new().unwrap();
    r.subscribe("com.lab126.powerd", Some("goingToScreenSaver"), |source, ev, intarg, strarg| {
        let res = publish_once("KINDLE", "iot.labs", "KINDLE/SCREEN_STATE", "0");
        if let res = Err(e) {
             println!("Failed to publish! {:?}", e),
        }
    })
    .unwrap();
}
```


# Final result

<video controls="true"><source src="/videos/kindle_light.mp4"/></video>


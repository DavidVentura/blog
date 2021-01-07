I have a paperwhite kindle on which I run a very dumb python script that broadcasts its' screen events (screen on, off) over the network, it's detailed [here](https://blog.davidventura.com.ar/integrating-a-kindle-into-house-automation.html).

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

```
[target.armv7-unknown-linux-gnueabi]
linker = "Amazon-Kindle-Cross-Toolchain/arm-kindle-linux-gnueabi/bin/arm-kindle-linux-gnueabi-cc"
```

Export the path to sysroot/lib before compiling:
```
export SYSROOT_LIB_DIR=~/git/Amazon-Kindle-Cross-Toolchain/arm-kindle-linux-gnueabi/arm-kindle-linux-gnueabi/sysroot/lib/
```

Running `cargo build` at this point fails, as `liblipc` itself needs to link to more shared
libraries.  
I copied the 3 needed libs from my kindle: `glib-2.0`, `dbus-1` and `gthread-2.0` into
the linker's search path (configured with `cargo:rustc-link-search=so`).

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

GetIntProperty: Pass a service, a filter property and a `int*` to get the current value
written to that address.

GetStringProperty: Pass a service, a filter property and a `char**` to get the current value
written to that address.

### Subscribe function

For `SubscribeExt` you also pass a service and a filter property, but along with them you send:

* A nullable pointer to a (callback) function that takes `char* name, Event* event, void* data` as arguments.
* A nullable pointer to anything, this is what `void* data` is on the previous line -- it's a way
  to send some context from the function that registers the callback to the called function.


This was quite tricky to get working without fully understanding, luckily `@pie_flavor` in the rust
discord helped me a lot.

The callback can't be passed directly - we have double box it; once to safely transport the type
data and once again to have a fixed-size object to reference.

# Avoiding parsing plain strings into results

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

---
title: Using translation models on mobile
date: 2025-01-10
tags: 
description: Implementing a "Google Translate" app with local models for Android, and losing my sanity along the way
incomplete: true
slug: mobile-translator
---

Disclaimer:

I have absolutely no idea what I'm doing when it comes to C++, CMake or Android, so it's likely that my struggles are user error.


Some time ago, Firefox [introduced]() in-browser, on-device translation for webpages. I know that Chrome users have had this forever,
but I'm not comfortable sending all my browsing data to Google.

This new feature was super useful for me, and I started wondering if I could also use it outside of the browser.


I did some research and found out that Mozilla publishes the [firefox-translation-models on GitHub](https://github.com/mozilla/firefox-translations-models/tree/main), and that
there's a piece of software called [bergamot-translator](https://github.com/browsermt/bergamot-translator) which can run these models, by wrapping [marian-nmt](https://marian-nmt.github.io)


With some basic idea of the software landscape, I tried it out

## Running bergamot-translator on Linux

```bash
$ git clone
$ mkdir build
$ sudo apt install libpcre2-dev libopenblas-dev
$ cmake ..
$ make -j
```

building was _fine_, but how to run this? I read a bunch of code for CI/tests/.. and figured out that I needed a YAML file exactly like this one:

```yaml
bergamot-mode: native
models:
  - firefox-translations-models/models/prod/esen/model.esen.intgemm.alphas.bin
vocabs:
  - firefox-translations-models/models/prod/esen/vocab.esen.spm
  - firefox-translations-models/models/prod/esen/vocab.esen.spm
shortlist:
    - firefox-translations-models/models/prod/esen/lex.50.50.esen.s2t.bin
    - false
beam-size: 1
normalize: 1.0
word-penalty: 0
max-length-break: 128
mini-batch-words: 1024
workspace: 128
max-length-factor: 2.0
skip-cost: true
cpu-threads: 0
quiet: false
quiet-translation: false
gemm-precision: int8shiftAlphaAll
alignment: soft
```

where `esen` is the language pair for the translation, in this case es&rarr;en (Spanish to English)


Now, the models/vocabs/shortlist files can be sourced from the `firefox-translations-models` repo with `git-lfs`, but I found it easier to
fetch the data from the Google storage endpoint (ironic, isn't it?), which is `https://storage.googleapis.com/bergamot-models-sandbox/0.3.1/{lang pair}/{file}`

With the models on hand, I could pipe some data through `bergamot-translator`:

```bash
echo "Hola mundo" | ./bergamot-translator
Hello world
```

At this point, I thought that converting this to a shared library would be trivial and I'd be done in _no time_.

## Android app scaffolding
I knew I would _easily_ build `libbergamot.so` for Android, so I downloaded Android studio, built a "Hello world" app and, through a bunch of clicking,
I added a "Native Library" module, which gave me _way too many files_, but here are the important ones:

`bergamot.cpp`, an adaptor from "Java calling convention" to "CPP calling convention" 
```cpp

extern "C" JNIEXPORT jstring JNICALL
Java_com_example_bergamot_NativeLib_stringFromJNI(
        JNIEnv* env,
        jobject /* this */) {
    return env->NewStringUTF("Hello from CPP");
}
```

`NativeLib.kt`, a Kotlin class wrapping the CPP adapter (obviously)

```kotlin
package com.example.bergamot

class NativeLib {
    external fun stringFromJNI(cfg: String, data: String): String
    companion object {
        // Used to load the 'bergamot' library on application startup.
        init {
            System.loadLibrary("bergamot-sys")
        }
    }
}
```

`CMakeLists.txt`, the build file for the cpp library:

```cmake
cmake_minimum_required(VERSION 3.22.1)
project("bergamot-sys")
add_library(${CMAKE_PROJECT_NAME} SHARED
        bergamot.cpp)

target_link_libraries(${CMAKE_PROJECT_NAME}
        # List libraries link to the target library
        android
        log
)
```

So, let's go build this `libbergamot`

## The descent into CMake madness

I thought that I only needed to do this

```diff
 add_library(${CMAKE_PROJECT_NAME} SHARED
         bergamot.cpp)

+add_subdirectory("bergamot-translator/")

 target_link_libraries(${CMAKE_PROJECT_NAME}
         # List libraries link to the target library
+        bergamot-translator
         android
         log
 )
```

and go on with my life.

Boy, was I wrong.

- Broken when trying to buld `aarch64`, okay just comment out
- no pcre2
- no openblas

## A despairing detour into WASM


## Out of WASM


- Add pcre2 flag local
- fuckit clone openblas in android SDK sysroot
- fuckit clone superlu in android SDK sysroot
- fuckit patch superlu

it... built???

```bash
file ..
x86
nm | grep func
found
```

## Loading the lib

`Fatal signal 4 (SIGILL), code 2 (ILL_ILLOPN)` on load

okay, add debugger in the Kotlin `NativeLib.kt` file, just `Debug.waitForDebugger()`

recompule in debug mode, it dies in some `set` stdlib operation?? wtf, it's some global about deprecated options, don't care, comment it out and rebuild

the shared lib loaded?????

Let's call the translate function

insta SIGILL again

with debugger see that it dies in similar stdlib operation, but this time i'm smart and run `disas` in `lldb`, get a dump of the running assembly:

```asm
...
...
vmovss ...
```

search for `vmovss`, it's an AVX instruction to do blah blah. wait. WAIT.

```bash
$ adb shell cat /proc/cpuinfo
emu64xa:/ $ 
processor       : 0
vendor_id       : AuthenticAMD
cpu family      : 6
model           : 6
model name      : Android virtual processor
cpuid level     : 16
flags           : fpu de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse ss
e2 ht syscall nx lm nopl cpuid tsc_known_freq pni ssse3 cx16 sse4_1 sse4_2 x2apic popcnt tsc_deadline_timer h
ypervisor lahf_lm cmp_legacy abm 3dnowprefetch vmmcall 
```

do you see it?? yeah, me neither!! `avx` is **not** part of the supported flags for the emulator's processor!!

## Trying to disable AVX at build time

I poked _a bunch_ and couldn't get AVX to stop being part of the build


## Giving up and enabling AVX on the emulator

There was no option in Android Studio to enable this, that I could find.. but I'm smarter than a shitty eclipse fork, so I started the emulator and ran 

```bash
$ ps aux | grep qemu

.../emulator/qemu/linux-x86_64/qemu-system-x86_64 -netdelay none -netspeed full -avd Medium_Phone_API_35 -qt-hide-window -grpc-use-token -idle-grpc-timeout 300 -no-snapshot-load
```

tried to run
```bash
./emulator/qemu/linux-x86_64/qemu-system-x86_64 ....

error while loading shared libraries: libtcmalloc_minimal.so.4: cannot open shared object file: No such file or directory
```

found the lib in `ANDROID_SDK/emulator/lib64`, so added I added that to `LD_LIBRARY_PATH`, but same thing with `libQt6WebChannelAndroidEmu.so.6`, repeating the process, adding `ANDROID_SDK/emulator/lib64/qt/lib` to `LD_LIBRARY_PATH`, the emulator starts up!

Reading the emulator's `--help`, I found out that there's a flag `-qemu ..` which passes all further arguments directly to qemu, so le'ts spawn an emulator with AVX support

```bash
cd $ANDROID_SDK/emulator
export LD_LIBRARY_PATH=$PWD/lib64:$PWD/lib64/qt/lib
./qemu/linux-x86_64/qemu-system-x86_64 -netdelay none -netspeed full -avd Medium_Phone_API_35 -qt-hide-window -grpc-use-token -idle-grpc-timeout 300 -no-snapshot-load -qemu -cpu "max"
```

once it starts up
```bash
$ adb shell grep -c avx /proc/cpuinfo
6
```

okay... let's try the app now

it doesn't crash??????

## Struggling to do basic tasks on Android

I don't know why, but I struggled a bunch to perform what should be absolutely trivial tasks.

Now that the app was launching, I needed to pass it some yaml (🤢) with paths to the models, and obviously, have the models stored there.

How do you even get a file to the emulator?? `adb push` didn't have access to the app's paths, and the app didn't have access to the "general storage" (/storage/emulated/0/...)

In the end, it was easier to implement some wacky code to download the files straight from Google (.\_.) if they are not present on disk

```kotlin
val base = "https://storage.googleapis.com/bergamot-models-sandbox/0.3.1"
val lang = "esen"
val model = "model.esen.intgemm.alphas.bin"
val vocab = "vocab.esen.spm"
val lex = "lex.50.50.esen.s2t.bin"
val files = arrayOf(model, vocab, lex)
val dataPath = baseContext.getExternalFilesDir("bin")!!

files.forEach { f ->
    val file = File(dataPath.absolutePath + "/" + f)
    if (!file.exists()) {
        val dm = this.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        val request = DownloadManager.Request(Uri.parse("${base}/${lang}/${f}"))
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
        request.setTitle("Downloading ${f}")
        val out = Uri.fromFile(file)
        request.setDestinationUri(out)
        val downloadReference = dm.enqueue(request) ?: 0
    }
}
```

Now I can also generate the YAML and call the function

```kotlin
val cfg = """
models:
  - ${dataPath}/${model}
vocabs:
  - ${dataPath}/${vocab}
  - ${dataPath}/${vocab}
shortlist:
    - ${dataPath}/${lex}
    - false
...
"""
val input = "Hola mundo"
val nl = NativeLib()
val output: String
val elapsed = measureTimeMillis {
    output = nl.stringFromJNI(cfg, input)
}
```


this worked!

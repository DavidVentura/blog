---
title: Building a GTK based mobile app
date: 2021-04-17
tags: gtk, python, rust
description: Learning GTK to build a mobile hackernews app, with ad-blocker and reader mode
---
<link href="/css/tabs.css" rel="stylesheet" type="text/css"/>

I ordered a [pinephone](https://www.pine64.org/pinephone/) and while waiting for it I wanted to see how hard it'd be to write basic mobile apps for
myself.

I picked [HN](https://news.ycombinator.com/) as it's a very simple site/api.

Features:

- Code blocks
- Embedded browser
  - Reader mode
  - Ad blocker

Lessons learned:

- Use a [resource bundle](https://developer.puri.sm/Librem5/Apps/Tutorials/App_Resources/Resource_File.html) for images / styles / etc.
- Use [ui files](https://python-gtk-3-tutorial.readthedocs.io/en/latest/builder.html) instead of programmatically adding all widgets
  - Connect the signals from the ui file (see example)
  - Use resources from the bundle directly on the ui file (see example)
- Using [grids](https://athenajc.gitbooks.io/python-gtk-3-api/content/gtk-group/gtkgrid.html) for content that is not homogeneous is a bad idea, it is better to use boxes-of-boxes.
- **Do not** use `GtkImage` along with `GtkEventBox`, use a `GtkButton` (probably with `flat` class).
- Use [libhandy](https://gitlab.gnome.org/GNOME/libhandy) for mobile-friendly widgets (or [libadwaita](https://gitlab.gnome.org/GNOME/libadwaita) if you are from the future and it's stable).
- [GTK Inspector](https://wiki.gnome.org/Projects/GTK/Inspector) is your friend.
- There's no general/defined way to connect events between widgets that are not direct parent-children. I went for a
  global [bus](https://github.com/DavidVentura/hn/blob/master/src/hn/bus.py) on which any widget can `emit` and `listen`
  for events.


Here's a very minimal example app that takes all of these into account, this is what I'd have liked to see as a "starting point" on the tutorials I've read.
You can find the source code [here](https://github.com/DavidVentura/blog/tree/master/blog/raw/building-a-gtk-app/).

The `resources.xml` file has to be compiled with `glib-compile-resources resources.xml --target resources`

<div class="tabset">
  <input type="radio" name="tabset" id="tab1" checked><label for="tab1">example.py</label>
  <input type="radio" name="tabset" id="tab2"><label for="tab2">MainWindow.ui</label>
  <input type="radio" name="tabset" id="tab3"><label for="tab3">resources.xml</label>
  
  <div class="tab-panels">
    <section class="tab-panel">
```python
{embed-file example.py}
```
    </section>
    <section class="tab-panel">
```xml
{embed-file MainWindow.ui}
```
    </section>
    <section class="tab-panel">
```xml
{embed-file resources.xml}
```
    </section>
  </div>
</div>

This is what it looks like:

![](/images/example-gtk-window.png)

## Adding a reader-mode button to the embedded browser

A feature I frequently miss when using embedded browsers is Firefox' [reader mode](https://support.mozilla.org/en-US/kb/firefox-reader-view-clutter-free-web-pages) button.  
Apparently this is [just some bits of javascript](https://github.com/mozilla/readability) so it should not be too hard to get an embedded browser to execute
them on demand.

In the [webkit docs](https://lazka.github.io/pgi-docs/WebKit2-4.0/classes/WebView.html) we can see that, while a bit clunky, it
is reasonable to use the callback-based APIs to execute some javascript:

Call `run_javascript_from_gresource(resource, None, callback, None)` on the WebView instance and get called back at
`callback` with a `resource` from which you can extract a result (via `run_javascript_from_gresource_finish`), a
complete example, showing how to get results from js functions:

```python
def on_readerable_result(resource, _result, user_data):
    result = www.run_javascript_finish(result)
    if result.get_js_value().to_boolean():
        print("It was reader-able")

def fn(resource, _result, user_data):
    result = resource.run_javascript_from_gresource_finish(result)
    js = 'isProbablyReaderable(document);'
    www.run_javascript(js, None, on_readerable_result, None)

www.run_javascript_from_gresource('/hn/js/Readability.js', None, fn, None)
```

This works great[^1]

## Adding an ad blocker to the embedded browser

Once you are using an embedded browser, you realize how much you miss Firefox' ad-blocking extensions, so I set out to
try and implement something similar (although, quite basic).

WebKit2 does not expose a direct way to block requests, see
[here](https://lists.webkit.org/pipermail/webkit-gtk/2013-March/001395.html). 
You need to build a WebExtension shared object, which webkit [can be instructed to load at runtime](https://github.com/DavidVentura/webextension-adblocker/blob/master/demo.py#L21) and *that WebExtension* can process / reject requests.

A WebExtension is exposed via a fairly simple [api](https://webkitgtk.org/reference/webkit2gtk/stable/ch02.html) which
allows us to connect to the few signals we are interested in:

* The `WebExtension` is initialized
* A `WebPage` object is created
* An `UriRequest` is about to be sent

The most basic possible example is available
[here](https://github.com/DavidVentura/webextension-adblocker/blob/13910676c6c8be64f11e4a0b80b76a02e1268aff/trivial_webext.c), as a small C program.

As I do not feel like I can write *any* amount of C code, I set out to build the extension in Rust, which offers a
relatively easy way to interop with C via [bindgen](https://github.com/rust-lang/rust-bindgen).

### Generating bindings

Bog standard bindgen use, following [the tutorial](https://rust-lang.github.io/rust-bindgen):

File `headers.h`

```c
#include <gtk/gtk.h>
#include <webkit2/webkit-web-extension.h>
```

Whitelist what I wanted in `build.rs`

```rust
let bindings = bindgen::Builder::default()
    // The input header we would like to generate
    // bindings for.
    .whitelist_function("g_signal_connect_object")
    .whitelist_function("webkit_uri_request_get_uri")
    .whitelist_function("webkit_web_page_get_id")
    .whitelist_function("webkit_web_page_get_uri")
    .blacklist_type("GObject")
    .whitelist_type("GCallback")
    .whitelist_type("WebKitWebPage")
    .whitelist_type("WebKitURIRequest")
    .whitelist_type("WebKitURIResponse")
    .whitelist_type("gpointer")
    .whitelist_type("WebKitWebExtension")
```

Add search paths

```rust
let gtk = pkg_config::probe_library("gtk+-3.0").unwrap();
let gtk_pathed = gtk
        .include_paths
        .iter()
        .map(|x| format!("-I{}", x.to_string_lossy()));

bindings.clang_args(webkit_pathed);
```

### Connecting signals

With the bindings generated we only need to connect the 3 required signals to our rust code, here's one as an
example[^2]:

```rust
#[no_mangle]
extern "C" fn webkit_web_extension_initialize(extension: *mut WebKitWebExtension) {
    unsafe {
        g_signal_connect(
            extension as *mut c_void,
            CStr::from_bytes_with_nul_unchecked(b"page-created\0").as_ptr(),
            Some(mem::transmute(web_page_created_callback as *const ())),
            0 as *mut c_void,
        );
    };
    wk_adblock::init_ad_list();
}
```

## Implementing the ad-blocker

We now have WebKit calling `init_ad_list` once, when initializing the web-extension (this is our actual entry point to the
extension logic) and `is_ad(uri)` *before* every request.

The ad-blocking logic is quite straight forward, requests should be blocked if

- The domain in the request considered 'bad'
- Any of the 'bad' URL fragments are present in the URL

Luckily a lot of people compile lists for both of these criteria. I've used the [pgl](https://pgl.yoyo.org/adservers/)
lists.

### Benchmarking implementations

I spent a while[^3] getting a benchmarking solution, [Criterion](https://bheisler.github.io/criterion.rs/book/getting_started.html), to work with my crate. When it finally did, I
compared the performance of a few algorithms:

For domain matching:

- A trie with reversed domains, as bytes (`b'google.com'` -> `b'moc.elgoog'`)
- A trie with reversed domains, as string arrays (`['google', 'com']` -> `['com', 'google']`)
- The [Aho-Corasick](https://en.wikipedia.org/wiki/Aho%E2%80%93Corasick_algorithm) algorithm for substring matching

For url-fragment matching:

- The [Twoway](http://www-igm.univ-mlv.fr/~lecroq/string/node26.html) algorithm for substring matching (both on bytes and on &str)
- The [Aho-Corasick](https://en.wikipedia.org/wiki/Aho%E2%80%93Corasick_algorithm) algorithm for substring matching
- Rust's `contains` (on &str)
- A very naive `window match` on bytes (compare every n-sized window of bytes with target)


The results really, really surprised me. The input files are ~19k lines for the subdomain bench and ~5k lines for the
fragment bench.


[![](/images/benchmarks-fragment.png)](/images/benchmarks-fragment.png)
<p class="center">URL fragment benches</p>
All methods are relatively similar at ~450us, except Aho-Corasick at 180ns (!!), clear winner.


[![blabla](/images/benchmarks-domain.png)](/images/benchmarks-domain.png)
<p class="center">Subdomain benches</p>
I'd expected the trie implementation to be fast (and I was quite happy when I saw the ~30us).. but the Aho-Corasick
algorithm is again at 140ns which is mind-blowing.


These timings are on my desktop pc, running on an [Odroid C2](https://wiki.odroid.com/odroid-c2/hardware/hardware) they are ~5x slower (subdomain benches clock at 850ns,
165us, 685us)[^4].

# The result

![](https://raw.githubusercontent.com/davidventura/hn/master/screenshots/comments.png?raw=true)

[^1]: Although it is a tad slow on a test device (2013 Nexus 5). I might evaluate later the performance of calling a [rust implementation](https://github.com/kumabook/readability) instead, and whether that's worth it or not.
[^2]: This is probably wrong on many levels, but I don't know any better
[^3]: Went insane before finding that [you can't use a cdylib crate](https://github.com/rust-lang/cargo/issues/6659) for integration tests.
[^4]: And I expect the pinephone to be another 2x slower - but it is still incredibly fast

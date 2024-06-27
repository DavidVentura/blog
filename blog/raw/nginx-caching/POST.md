---
title: nginx, caching and X-Accel-Redirect
date: 2017-06-29
tags: nginx
description: 
---
Nginx is awesome. I use it everywhere, for load balancing, file caching, reverse-proxying, rate-limiting, etc.

Now, I'm trying to cache a file served from an X-Acccel-Redirect header and it seems impossible.

My idea was to resolve requests to files in a back-end and serve these files **without** a client redirect. In fact, the original files are **not** accessible by the client.

For example, accessing `/v/uri-example-1` would get internally mapped to the file `/nfs/file-1`, but the same file would be the response to `/v/uri-example-2`, and of course, the back-end has to authenticate the users.

The `X-Accel-Redirect` header was made for this.

> NGINX will match this URI against its locations as if it was a normal request. It will then serve the location that matches the defined root + URI passed in the header.

[Source](https://www.nginx.com/resources/wiki/start/topics/examples/x-accel/)

This, of course, works perfectly.

The problem arises when you try to cache a response with `X-Accel-Redirect` header. Because you can't. The nginx caching mechanism is disabled if this header is present.

There are some ugly hacks that are supposed to 'fix' this.

The idea behind these hacks is to have 2 'levels', one ignores the `X-Accel-Redirect` header and caches the data while proxying to the next level, the other one actually processes the request (In the example, `/v/uri-example-1` -> `/nfs/file-1` )

Hack #1 (advised [here](http://mailman.nginx.org/pipermail/nginx/2017-January/052732.html))

```nginx
proxy_cache_path /cache/nginx levels=1:2 keys_zone=cache:10m inactive=24h;

upstream backend {
    server unix:///tmp/streaming-backend.sock;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    include /etc/nginx/ssl;
    server_name _;
    gzip off;

    proxy_cache_min_uses 1;
    proxy_cache cache;
    proxy_cache_valid 200 24h;

    location /v/ {
        rewrite /v/(.+) /$1 break;
        uwsgi_pass backend;
        include uwsgi_params;

        proxy_set_header   X-Real-IP       $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /converted/ {
        proxy_pass http://127.0.0.1:9999/converted/;
        proxy_request_buffering off;
        proxy_ignore_headers X-Accel-Expires Expires Cache-Control Set-Cookie;
    }

}

server {
    listen 127.0.0.1:9999;
    location /converted/ {
        root /nfs/;
    }
}
```

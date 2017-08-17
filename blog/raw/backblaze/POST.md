I've been trying to move our video content from youtube to our own server, but keeping in mind that we add about ~40GB / Month to our collection (and it never goes away..) and that DigitalOcean's disks are not very cheap, I decided to serve our videos directly from Backblaze.

Currently there's no CORS support on B2 ( https://help.backblaze.com/hc/en-us/articles/114094192774-Does-B2-have-CORS-headers-support- )

Backblaze recommends using Cloudflare as an SSL termination endpoint ( https://help.backblaze.com/hc/en-us/articles/217666928-Creating-a-Vanity-URL-with-B2 ) and using them as DNS to host stuff on your own domain. We'd rather not use Cloudflare.


So I ended up setting up a reverse caching proxy between B2 and my service:

nginx.conf:
```nginx
proxy_cache_path /var/nginx-cache levels=1:2 keys_zone=my_cache:10m max_size=15g inactive=48h max_size=10g use_temp_path=off;
```
...
```nginx
    location /cdn/ {
        proxy_set_header X-Real-IP  $remote_addr;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffers 16 4k; 
        proxy_buffer_size 2k; 

        proxy_cache my_cache;
        proxy_cache_revalidate on; 
        proxy_cache_min_uses 1;
        proxy_cache_lock on; 
        proxy_ignore_headers Cache-Control;
        add_header X-Cache-Status $upstream_cache_status;
        proxy_cache_valid any 48h;

        proxy_pass https://f001.backblazeb2.com/my-endpoint/;
    } 
```

Which works pretty nicely and even reduces part of the latency from B2. Considering this is hosted on a $5 DigitalOcean VPS and I get 1TB of traffic per month for free (which is below our current traffic) I end up saving money from B2.

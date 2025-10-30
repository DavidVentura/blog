---
date: 2025-10-30
title: Geo-distributed blog for $7/mo
tags: meta
description: Just needed to sell my soul to Jeff
slug: geo-distributed-blog
---

Recently I got the itch to try and see if I could make this site load quicker, and even though there's not much to do
from a content perspective (pages are ~5KiB of content, static files have long caches), the largest
amount of time spent was purely latency based, as this site was served only from Germany, if you were not close
then you are going to have to wait a bit.

The only way to reduce latency[^transport-medium] is to put the devices that are communicating closer.

[^transport-medium]: Well, you can always try to use a transport medium with a lower light propagation delay, but it's going to cost a few billion

Moving this server to any other point wouldn't make much sense, the only option is to have multiple servers in 
different parts of the world.

As far as I know, the proper way to do this is to have a single IP shared between multiple DNS servers in different locations,
then through [Anycast](https://en.wikipedia.org/wiki/Anycast), the client would route to the "closest" server.

<div class="aside">
"closest" is in quotes because it's not measured by geographical distance, but rather it's a property set by network operators on each physical link.
<br/>
In an ideal world, the cost would match (latency ✕ bandwidth) of the link, but sometimes there are economic deals that make traffic cheaper through slower links.
</div>


I couldn't really find an operator that would sell me an Anycast "service" or even VPS with Anycast IPs. Building this myself would require buying a `/24` IP block (255 IPv4 addresses) for $5-10k, find a few VPS vendors that also provide BGP services to announce my IP range.

That would be ideal, but it's a bit out of budget[^budget] for a side project; Sadly, I took the more pragmatic route:
paying for a DNS service which handles this internally.

[^budget]: I would definitely consider a "group buy" of an IP block; $20-40 for my own IP sounds great.

I tried a few options:

[dnsimple](https://dnsimple.com/) promised a nice hobby tier, but gates the GeoDNS records behind $50/mo.

[Gcore](https://gcore.com/dns) offers a nice free plan, to try it out, I made [a script](https://github.com/DavidVentura/http-measurement)
using [fly.io](https://fly.io) to spawn machines all over the world and measure the perceived latency.

However, I kept seeing this pattern:

![](assets/ams_small.png)

Enriched with `response region`:

|client region | response region | total duration ms |   ip address   |
|--------------|-----------------|-------------------|-----------------
|ams           | DE              |         67.077893 | 139.178.72.187 |
|ams           | DE              |         66.384035 | 216.246.119.90 |
|ams           | DE              |         67.950036 | 216.246.119.114|
|ams           | DE              |         66.065846 | 139.178.72.187 |
|ams           | LAX             |        847.931087 | 216.246.119.86 |
|ams           | DE              |         66.322204 | 216.246.119.89 |
|ams           | DE              |         67.290175 | 216.246.119.90 |
|ams           | LAX             |        818.730120 | 216.246.119.86 |
|ams           | DE              |         64.972008 | 139.178.72.187 |
|ams           | DE              |         66.102748 | 139.178.72.187 |

Some of the requests are served from the wrong region (`LAX` in the previous table). I assume[^gaslight] that Gcore's GeoDNS service uses some kind of reverse-lookup
database to determine where the clients are, and which record to return.

[^gaslight]: Maybe it was Fly.io gaslighting me and giving me a server in USA when I asked for one in Amsterdam, but that sounds very unlikely

I don't think this is a good way to implement location-aware DNS: those databases go out of date, and most importantly the concept of "to which physical location this address belongs to" does not make sense.


The right way to do this is to use the _DNS server_'s geographical location for the decision, the user will be routed to the "closest" DNS server thanks to BGP anyway &mdash; given a sufficient number of {^POPs|points of presence}, the DNS server's location is a pretty good proxy for the user's location.

The only provider that offers this feature, as far as I know, is AWS' Route53, so that's what I am using now.

If you know of another DNS provider with this feature, please let me know.


## Providers and costs

For servers, I picked [Greencloud](https://greencloudvps.com/) for my VPS in Singapore ($25/year) and [Racknerd](https://www.racknerd.com/kvm-vps) for the VPS in Texas, USA ($12/year). I was already using [Hetzner](https://www.hetzner.com/cloud/) for my VPS in Germany ($36/year)

DNS is Route53, which costs $6/year.

The grand total is $7/month.

## Results

Was it worth it? Yes! Average latency is below 100ms[^pingcdn] from any[^locations] location

[^pingcdn]: According to some random [Keycdn](https://tools.keycdn.com/ping) ping test
[^locations]: If you carefully pick your locations to exclude South America, South Africa and New Zealand

| Location           |Resolved (before)| AVG (before) | Resolved (after) | AVG (after) | Delta (rounded to 10ms) |
|--------------------|-----------------|-----------|----------------|-----------|--------------|
| 🇩🇪 Frankfurt     | 78.46.233.60    | 18ms  | 78.46.233.60   |  20ms  | No change |
| 🇳🇱 Amsterdam     | 78.46.233.60    | 13ms  | 78.46.233.60   |  11ms | No change |
| 🇬🇧 London        | 78.46.233.60    | 19ms  | 78.46.233.60   |  19ms | No change |
| 🇺🇸 New York      | 78.46.223.60    | 87ms  | 155.94.173.109 |  35ms | -50ms |
| 🇺🇸 San Francisco | 78.46.223.60    | 159ms | 155.94.173.109 |  44ms | -150ms |
| 🇸🇬 Singapore     | 78.46.223.60    | 172ms  | 96.9.213.82    |  1.52 ms  | -170ms |
| 🇦🇺 Sydney        | 78.46.223.60    | 274ms | 96.9.213.82    |  93ms | -180ms |
| 🇮🇳 Bangalore     | 78.46.223.60    | 183ms | 96.9.213.82    |  38ms | -150ms |

This page should now load much faster; establishing a TLS connection requires 3&ndash;4 roundtrips, so for someone in San Francisco {^TTFB|time to first byte} is now ~175ms, instead of ~650ms.

## Operational complications

I use [Caddy](https://github.com/caddyserver/caddy) as my HTTP server, which will by default, ask [Let's Encrypt](https://letsencrypt.org/) for SSL certificates.

I was using the [HTTP-01](https://letsencrypt.org/docs/challenge-types/#http-01-challenge) challenge, which performs a GET request to `/.well-known/acm-echallenge/<TOKEN>`, but now that doesn't work anymore &mdash; all requests get directed to the Texas server, and that server does not know about requests performed by the other two servers.

The easy option would be to change and use the [DNS-01](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge) challenge, but that would require all 3 of my servers to have keys to manage my DNS records, and I don't want to trust a $10/year VPS provider with my keys.

Instead, I opted for disabling SSL certificate management in my "secondary" servers, and ship the certificates from the "main" server to them.

This is the caddy config for the secondary servers:

```text
blog.davidv.dev {
    tls /var/lib/caddy/blog.davidv.dev.crt /var/lib/caddy/blog.davidv.dev.key
    header +region {$REGION}
    import blog_common
}
```

and a cron job on the primary server to distribute the certificates:

```bash
scp $CERT root@blog.sg.davidv.dev:/var/lib/caddy/
scp $KEY root@blog.sg.davidv.dev:/var/lib/caddy/
ssh root@blog.sg.davidv.dev "chown caddy /var/lib/caddy/blog.davidv.dev.*"
ssh root@blog.sg.davidv.dev "systemctl reload caddy"
```


## But why not Cloudflare?

Cloudflare offers a free (as in, $0) service for this kind of thing, but I don't believe they should control any more of the internet. Friends don't let friends use Cloudflare.

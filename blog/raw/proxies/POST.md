Serving content over https is trivial, right?

It's not so trivial if you want to learn about HA and keep everything working with SSL.

This is how my current setup is working:

1. The inbound TCP connections on port 443 get scanned with `sslh` and redirected based on the protocol, SSL connections get redirected to the LoadBalancers via  Round Robin DNS.
2. The LoadBalancers decide where the connection should go (I'm using sticky sessions).
3. The request might be:
  1. HTTP
     - If it is a Lets Encrypt request, it gets redirected to the central certificate manager
     - Else it gets a 301 to the HTTPS site
 2. HTTPS
     - The request gets dispatched to a reverse proxy
4. The reverse proxy finally dispatches the request to the application server (which most of the time are actually HTTP servers).


Some typical requests end up doing something like:

```
SSL  request -> DNS -> LB1 -> ReverseProxy1 -> AppServer1
SSL  request -> DNS -> LB2 -> ReverseProxy3 -> HTTP server
HTTP request -> DNS -> LB1 -> Certificate Manager
HTTP request -> DNS -> LB2 -> 301 to HTTPS
```

The certificate manager has a cron entry scheduled to run `certbot` every 5 days, and on a successful certificate renewal, the files get deployed to the LoadBalancers

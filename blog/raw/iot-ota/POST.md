
After setting up my lamp I realized that I had left the built in LED permanently on. For a nightlamp, this is extremely annoying and given that taking it apart was going to be a hassle, I decided to do it for one last time and do it right.

# The plan

The simplest way I could think of was to replace a file in the VFS of the sensors so that it gets reloaded on reboot.

For this, I needed to send:

* the file contents
* file name 
* some sort of hash to verify that the transfer was successful

# Picking the hash

This was easy. MicroPython on the esp8266 only supports SHA1 and MD5 ([this](http://docs.micropython.org/en/latest/esp8266/library/uhashlib.html?highlight=hashlib#module-uhashlib) says that there is support for SHA256 but it wasn't implemented on my version), so SHA1 it is.

# First attempt
The first thing I tried was to simply send all the data as JSON via MQTT. This failed miserably to allocate memory to decode even 1.2KB files.

# Second attempt
My next idea was to use a "simple" fixed-length string followed by the file contents, something like
```
filename|hash|contents
```
and send that over MQTT, the first and biggest issue with this is that the MQTT client is not streaming the downloads, so we could fit **at most** a 4KB file.

Even if we ignored the 4KB per file limit, when doing manipulation on the buffers it resulted in either complete or partial copies, which also made me run out of memory.

# Final solution

I finally realized I needed to stream the file contents straight to the VFS, so I decided to implement something similar to IRC's DCC:

On the server:

* Send via MQTT a pipe-delimited string containing: Hostname, port, filename and hash
    * This message is only sent to a single sensor
* Start a socket and serve the file (as binary data) to the first client that connects.

On the ESP:

* When receiving the OTA update message, connect to the specified `HOST:PORT`
* Download the file in chunks
    * write each chunk straight to disk in a `tmp` file
    * update the local hash object with the chunk contents
* Compare the received hash and the locally calculated one, if they match, rename the temporary file-buffer to the file specified previously
* Reboot

Doing the download this way the maximum amount of file-data I keep in memory is the socket buffer size (536 bytes by default). The whole OTA update for a 3.8KB file takes <100ms (The reboot, AP association and obtaining a DHCP lease can take up to 5 seconds though).

# Transparent updates

A big factor on the development of this framework is that plugins shouldn't need to know anything about the base system and its functions.

This is why the `setup` of the `common` file will 'hijack' the topic `HOSTNAME/OTA` and trigger this behaviour.

You can see the details and implementation [here](https://github.com/DavidVentura/iot_home/blob/master/firmware/common.py#L73) for the ESP and [here](https://github.com/DavidVentura/iot_home/blob/master/server/OTA_sender.py) for the sender/server.


# Security note

There's no authentication or encryption involved. Given the range and scope of this deployment(isolated VLAN, only I have access), it is fine.

# Extra
These little modules seem to output quite a lot of heat, I initially had taped the DHT22 to it but the result was this

![](/images/dht-temp.png)

The taped period is ~2230-2345

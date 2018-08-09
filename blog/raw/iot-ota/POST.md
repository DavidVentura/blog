
After setting up my lamp I realized that I had left the built in LED permanently on. For a nightlamp, this is extremely annoying, and given that taking it apart was going to be a hassle I decided to do it for one last time and do it right.

# The plan

I wanted to be able to replace a file in the VFS of the sensors remotely.

For this, I needed to send the file contents, file name and some sort of hash to verify that the transfer was successful (and to avoid bricking the device on a partial transfer).

# Picking the hash

This was easy. MicroPython on the esp8266 only supports sha1 and md5 ([this](http://docs.micropython.org/en/latest/esp8266/library/uhashlib.html?highlight=hashlib#module-uhashlib) says that there is support for sha256 but it wasn't implemented on my version), so sha256 it is.

# First attempt
The first thing I tried was to simply send all the data as JSON via MQTT. This failed miserably to decode even with 1.2KB files.

# Second attempt
My next idea was to use a "simple" fixed-length string followed by the file contents, something like
```
filename|hash|contents
```
and send that over MQTT, the first and biggest issue with this is that the MQTT client is not streaming the downloads, so we could fit at most a 4KB file.

The second issue I faced with this approach was that when doing manipulation on the buffers it resulted in either complete or partial copies, which also made me run out of space.

# Final solution

I realized I needed to stream the file contents straight to disk, so I decided to implement something similar to IRC's DCC:

On the server:

* Send via mqtt a pipe-delimited string containing: Hostname, port, filename and hash
* start a socket and serve the file as binary data to the first client that connects.

On the ESP:

* When I receive this message I connect to the specified `HOST:PORT`
* Download straight to disk in a tmp file, while updating the local hash object
* Compare hashes, if they match, rename the temp file to the value obtained previously
* Reboot

Doing the download this way the maximum amount of file-data I keep in memory is the socket buffer size (536 bytes by default).

# Transparent updates

A big factor on the development of this framework is that plugins shouldn't need to know anything about the base system and its functions; that's why the `setup` of the common file will hijack the topic `HOSTNAME/OTA` and trigger this behaviour.

You can see the details and implementation [here](https://github.com/DavidVentura/iot_home/blob/master/firmware/common.py#L73) for the ESP and [here](https://github.com/DavidVentura/iot_home/blob/master/server/OTA_sender.py) for the sender/server.


# Security note

There's no authentication or encryption involved. Given the range and scope of this deployment(isolated VLAN, only I have access), it is fine.

# Extra
These little modules seem to output quite a lot of heat, I initially had taped the DHT22 to it but the result was this

![](images/dht-temp.png)

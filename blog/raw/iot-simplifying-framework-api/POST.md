---
title: Simplifying the IOT framework's API
date: 2019-07-11
tags: iot, changelog
description: A small refactor in my IOT framework with the goal of simplifying the API
---
This post is more of a changelog combined with an explanation of my thought process for the changes.  

[c50b112](https://github.com/DavidVentura/iot_home/commit/c50b112) - Use the `publish` function only from `common` instead of directly from `mqtt`. Doing this removes the requirement from the client to verify if the `mqtt` object has been initialized.

[d6df15c](https://github.com/DavidVentura/iot_home/commit/d6df15c), [8a3d443](https://github.com/DavidVentura/iot_home/commit/8a3d443) - Add logging on OTA updates & log using explicit indexes on OTA updates, this allows extra fields to be sent (and ignored).

[f576c69](https://github.com/DavidVentura/iot_home/commit/f576c69) - Require subscription topics to be provided as a list, this simplifies client setup. Move OTA logic out of mqtt client creation

[f2b03bb](https://github.com/DavidVentura/iot_home/commit/f2b03bb), [219e560](https://github.com/DavidVentura/iot_home/commit/219e560) - Ignore and remove `_id` argument in `loop` &ndash; we can now obtain that from a file called `HOSTNAME` (or fall back to the device's MAC address).

[5a59852](https://github.com/DavidVentura/iot_home/commit/5a59852), [fba9be8](https://github.com/DavidVentura/iot_home/commit/fba9be8) - Make rebooting optional while doing OTA. This allows you to push changes across multiple files, that otherwise would be backwards incompatible.

[1a93289](https://github.com/DavidVentura/iot_home/commit/1a93289), [a9a6911](https://github.com/DavidVentura/iot_home/commit/a9a6911) - Restructure layout for easier multi-file update

```bash
$ tree firmware
firmware/
├── common.py
├── curtains
│   ├── common.py -> ../common.py
│   ├── HOSTNAME
│   ├── main.py
│   └── mqtt.py -> ../mqtt.py
├── mqtt.py
└── rfsocket.py
```

With this setup, you can cd into a device's directory and run  
`mpfshell ttyUSB0 -c 'put common.py; put main.py; put mqtt.py; put HOSTNAME; repl'`  
to bootstrap a new device.  
Subsequent updates can be done OTA.

[fdf76d9](https://github.com/DavidVentura/iot_home/commit/fdf76d9) - Set hostname in AP config &ndash; this change makes it more clear which device is which on network inspection, there's no longer a list of ESP-8D... devices.


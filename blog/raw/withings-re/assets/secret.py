#!/usr/bin/env python3
import hashlib
from binascii import unhexlify

def calculate_challenge_response(challenge_hex, mac_address, kl_secret):
    combined = unhexlify(challenge_hex) + mac_address.encode() + kl_secret.encode()
    return hashlib.sha1(combined).hexdigest().upper()

# data from watch
challenge = "3FE94B29BD69F0A3FE2B0B18401941CF"
mac = "a4:7e:fa:44:d6:10" # watch mac
secret = "gUf8Np69A4GvJxjY1XOcIHKQm2HcPZnO"

response = calculate_challenge_response(challenge, mac, secret)
print(f"Watch Response:       {response}")

# data from phone
challenge = "69BDB44D10ECB2EB5A6E06960ECD066C"
mac = "a4:7e:fa:44:d6:10" # also watch mac, wtf
secret = "gUf8Np69A4GvJxjY1XOcIHKQm2HcPZnO"

response = calculate_challenge_response(challenge, mac, secret)

print(f"Phone Response:       {response}")

FROM debian:stretch
RUN apt-get update && apt-get -y --no-install-recommends install python3 python3-wheel python3-pip python3-setuptools markdown
RUN pip3 install tinys3
WORKDIR "/root/"
ENTRYPOINT /usr/bin/python3 /root/scripts/test.py

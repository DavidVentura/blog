FROM debian:stretch
RUN apt-get update && apt-get -y --no-install-recommends install python3 python3-wheel python3-pip python3-setuptools python3-jinja2
RUN pip3 install tinys3 markdown2 pygments
WORKDIR "/root/"
# RUN mkdir -p html && pygmentize -S default -f html > html/style.css
ENTRYPOINT /usr/bin/python3 /root/scripts/test.py

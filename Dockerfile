FROM ubuntu:bionic AS base

RUN apt-get update && \
    apt-get install -y \
	build-essential \
	python3.7 \
        python3-pip \
    && \
    rm -rf /var/lib/apt/lists/*

RUN python3.7 -m pip install \
    Pillow \
    pywavefront \
    dnspython \
    requests

WORKDIR /opt
ARG ospray_version=1.8.5
COPY ospray-${ospray_version}.x86_64.linux.tar.gz /tmp/
RUN tar xvf /tmp/ospray-${ospray_version}.x86_64.linux.tar.gz --strip-components 1 -C /usr && \
    rm /tmp/ospray-${ospray_version}.x86_64.linux.tar.gz

WORKDIR /opt/app
COPY server.c ./
RUN make \
	CFLAGS='-Wall -Werror -pedantic' \
	LDLIBS='-lospray' \
	server


FROM base AS dist

WORKDIR /opt/app
COPY server.py ./
COPY static ./static

ENTRYPOINT []
CMD []

FROM ubuntu:bionic AS base

RUN apt-get update && \
    apt-get install -y \
	build-essential \
	cmake \
	libopenmpi-dev \
	libopenimageio-dev \
	pkg-config \
	make \
	cmake \
	build-essential \
	libz-dev \
	libtbb-dev \
	libglu1-mesa-dev \
	freeglut3-dev \
	libnetcdf-c++4-dev \
	xorg-dev \
        x11-apps \
	xauth \
	x11-xserver-utils \
	vim \
	libjpeg-dev \
	imagemagick \
	python3.7 \
        python3-pip \
    && \
    rm -rf /var/lib/apt/lists/*

RUN python3.7 -m pip install \
    Pillow \
    pywavefront

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

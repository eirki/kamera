FROM python:3.7-slim-stretch

RUN apt-get -y update \
    && apt-get install -y --fix-missing --no-install-recommends \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    curl \
    graphicsmagick \
    libgraphicsmagick1-dev \
    libatlas-dev \
    libavcodec-dev \
    libavformat-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libswscale-dev \
    pkg-config \
    python3-dev \
    python3-numpy \
    software-properties-common \
    zip \
    && apt-get clean && rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/*


# https://hub.docker.com/r/dylansm/exiftool/dockerfile/
ENV EXIFTOOL_VERSION=10.20
RUN apt-get install -y --fix-missing --no-install-recommends perl make
RUN cd /tmp \
	&& wget http://www.sno.phy.queensu.ca/~phil/exiftool/Image-ExifTool-${EXIFTOOL_VERSION}.tar.gz \
	&& tar -zxvf Image-ExifTool-${EXIFTOOL_VERSION}.tar.gz \
	&& cd Image-ExifTool-${EXIFTOOL_VERSION} \
	&& perl Makefile.PL \
	&& make test \
	&& make install \
	&& cd .. \
	&& rm -rf Image-ExifTool-${EXIFTOOL_VERSION}

RUN adduser --disabled-login --gecos '' kamerauser

RUN mkdir -p /home/kamerauser/app
WORKDIR /home/kamerauser/app
RUN python -m venv venv

# preinstall dlib so it's cached before requirements.txt install
RUN mkdir -p dlib && \
    git clone -b 'v19.18' --single-branch https://github.com/davisking/dlib.git dlib/ && \
    cd  dlib/ && \
    ../venv/bin/python setup.py install && \
    cd .. && \
    rm -r dlib

COPY requirements.txt requirements.txt
RUN venv/bin/pip install -r requirements.txt

USER kamerauser

COPY kamera kamera

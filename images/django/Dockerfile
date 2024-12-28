FROM python:3.8

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TZ=Europe/Moscow

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Clean and update package lists
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN apt-get update

# Install necessary packages
RUN apt-get install -y gcc libc-dev libpq-dev

# Autoclean and remove unnecessary files
RUN apt-get -y autoclean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Upgrade pip and install requirements
RUN pip install --upgrade pip --no-cache-dir
COPY ./app/requirements.txt /tmp/
COPY ./.env /.env
RUN pip install -q -Ur /tmp/requirements.txt

WORKDIR /app


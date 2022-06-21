FROM python:3.8

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN  apt-get update && \
     apt-get install -y  gcc libc-dev libpq-dev && \
     apt-get -y autoclean && \
     rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY ./app/requirements.txt /tmp/
COPY ./.env /.env

RUN pip install -U pip
RUN pip install -Ur /tmp/requirements.txt


WORKDIR /app

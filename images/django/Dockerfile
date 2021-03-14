FROM python:3

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone


COPY ./app/requirements.txt /tmp/

RUN pip install -U pip
RUN pip install -Ur /tmp/requirements.txt

WORKDIR /app

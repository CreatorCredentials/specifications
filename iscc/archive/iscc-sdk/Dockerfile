# Use a base image that supports both Python and Rust
FROM rust:latest

RUN cargo install c2patool

# Install Python
RUN apt-get update && \
    apt-get install -y python3.10
RUN apt-get install -y python3-pip
RUN apt-get install -y python3-poetry

RUN mkdir /app
COPY . /app
WORKDIR /app
ENV PYTHONPATH=${PYTHONPATH}:${PWD} 
# RUN pip3 install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --only main
RUN ln -s /usr/bin/python3 /bin/python

# FROM python:3.10
# RUN mkdir /app
# COPY . /app
# WORKDIR /app
# ENV PYTHONPATH=${PYTHONPATH}:${PWD} 
# RUN pip3 install poetry
# RUN poetry config virtualenvs.create false
# RUN poetry install --only main

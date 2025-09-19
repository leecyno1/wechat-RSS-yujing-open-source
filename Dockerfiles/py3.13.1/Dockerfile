FROM ghcr.io/rachelos/base:latest
ENV PIP_INDEX_URL=https://mirrors.huaweicloud.com/repository/pypi/simple
WORKDIR /app
RUN ls
COPY  requirements.txt .
RUN pip3 install -r requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple


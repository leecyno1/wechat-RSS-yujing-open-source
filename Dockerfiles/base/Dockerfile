FROM docker.1ms.run/ubuntu:20.04
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y wget build-essential zlib1g-dev libncurses5-dev \
    libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://mirrors.huaweicloud.com/python/3.13.1/Python-3.13.1.tar.xz \
    && tar -xf Python-3.13.1.tar.xz \
    && cd Python-3.13.1 \
    && ./configure --enable-optimizations \
    && make -j$(nproc) \
    && make altinstall \
    && cd .. \
    && rm -rf Python-3.13.1.tar.xz Python-3.13.1

RUN ln -s /usr/local/bin/python3.13 /usr/local/bin/python3 \
    && ln -s /usr/local/bin/pip3.13 /usr/local/bin/pip3


# 自动设置时区（如上海）
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN apt update&&apt install -y --no-install-recommends firefox 
RUN apt install  -y git
RUN apt clean&&apt autoremove -y&&rm -rf /var/lib/apt/lists/*
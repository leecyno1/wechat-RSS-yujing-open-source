FROM docker.1ms.run/ubuntu:18.04
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV DEBIAN_FRONTEND=noninteractive
# RUN apt update
RUN apt install -y python3 
RUN apt install -y python3-pip

# 自动设置时区（如上海）
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
RUN apt install -y --no-install-recommends firefox 

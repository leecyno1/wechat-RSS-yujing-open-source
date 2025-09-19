echo off
chcp 65001
for /f "tokens=1 delims==" %%v in ('python -c "from core.ver import VERSION; print(VERSION)"') do set VERSION=%%v
set tag="v%VERSION%"
echo 当前版本: %VERSION% TAG: %tag%
set name=we-mp-rss:%VERSION%
docker build -t %name% .
REM 获取所有运行中容器的ID并逐个停止
FOR /f "tokens=*" %%i IN ('docker ps -q') DO docker stop %%i
docker container prune -f
docker run -d --name we-mp-rss -e GIT_UPDATE=true -p 8002:8001 -v %~dp0:/work %name%
docker exec -it we-mp-rss /bin/bash

if "%1"=="-p" (
docker image tag %name% ghcr.io/rachelos/%name%
docker image ls
docker push ghcr.io/rachelos/%name%
)
docker stop we-mp-rss
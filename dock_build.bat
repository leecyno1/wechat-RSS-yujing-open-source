echo off
chcp 65001
set VERSION=latest
set platform=linux/amd64,linux/arm64
echo 当前版本: %VERSION%
set name=we-mp-rss:%VERSION%
if "%1"=="-test" (
docker stop we-mp-rss
docker stop we-mp-rss-arm
docker rm we-mp-rss
docker rm we-mp-rss-arm
docker run -d --name we-mp-rss --platform linux/amd64 -p 8002:8001 -v %~dp0:/work %name%
docker run -d --name we-mp-rss-arm --platform linux/arm64 -p 8003:8001 -v %~dp0:/work %name%
goto :eof
)
REM 检查并创建 buildx builder
docker buildx inspect multiarch >nul 2>&1
if errorlevel 1 (
    echo 创建多架构构建器...
    docker buildx create --name multiarch --use --platform %platform%
) else (
    echo 使用现有的多架构构建器...
    docker buildx use multiarch
)

echo 开始构建多架构镜像 (%platform%)... %name%
REM 先构建并加载本地架构的镜像
docker buildx build --platform %platform% -t %name% --load .
echo 构建完成: %name%
echo 检查镜像架构信息:
docker inspect %name%|find "arm64"

REM 获取所有运行中容器的ID并逐个停止
FOR /f "tokens=*" %%i IN ('docker ps -q') DO docker stop %%i
docker container prune -f
docker image prune -f
docker image ls
REM 运行容器 (使用本地架构)
docker run -d --name we-mp-rss -platform linux/amd64 -p 8002:8001 -v %~dp0:/work %name%
docker run -d --name we-mp-rss-arm --platform linux/arm64 -p 8003:8001 -v %~dp0:/work %name%
@REM docker exec -it we-mp-rss /bin/bash
@REM docker stop we-mp-rss

if "%1"=="-p" (
    echo 推送多架构镜像到仓库...
    docker buildx build --platform %platform% -t ghcr.io/rachelos/%name% --push --insecure .
    docker image ls
)

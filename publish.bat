@echo off
chcp 65001
if "%1"=="-web" (
    cd web_ui
    call build.bat
    cd ../
)
REM 读取Python配置文件中的版本号
for /f "tokens=1 delims==" %%v in ('python -c "from core.ver import VERSION; print(VERSION)"') do set VERSION=%%v
set tag="v%VERSION%"
echo 当前版本: %VERSION% TAG: %tag%

set comment="%1"
set version_file="docs/versions/%VERSION%"
if exist %version_file% (
    for /f "usebackq delims=" %%a in (%version_file%) do set comment=%%a
) else (
    echo 警告：未找到对应版本号的文件 %version_file%
)

if "%1"=="-p" (
    git push -u origin main 
    git push origin  %tag%
    git push -u gitee main
    git push gitee  %tag%
) else (
    echo %comment%
    git add .
    git tag  "v%VERSION%" -m "%comment%"
    git commit -m "%VERSION%-%comment%"
)
@echo off
chcp 65001

REM 初始化参数标志
set WEB_FLAG=0
set PUSH_FLAG=0
set COMMENT_FLAG=0

REM 解析参数
:parse_args
if "%~1"=="" goto end_args

if "%~1"=="-web" (
    set WEB_FLAG=1
) else if "%~1"=="-p" (
    set PUSH_FLAG=1
) else if "%~1"=="-m" (
    set COMMENT_FLAG=1
    set USER_COMMENT="%~2"
    shift
)
shift
goto parse_args

:end_args

REM 执行-web操作
if %WEB_FLAG%==1 (
    cd web_ui
    call build.bat
    cd ../
)

REM 读取Python配置文件中的版本号
for /f "tokens=1 delims==" %%v in ('python -c "from core.ver import VERSION; print(VERSION)"') do set VERSION=%%v
set tag="v%VERSION%"
echo 当前版本: %VERSION% TAG: %tag%

REM 设置comment
if %COMMENT_FLAG%==1 (
    set comment=%USER_COMMENT%
) else (
    set comment="%VERSION% release"
    set version_file="docs/versions/%VERSION%"
    if exist %version_file% (
        for /f "usebackq delims=" %%a in (%version_file%) do set comment=%%a
    ) else (
        echo 警告：未找到对应版本号的文件 %version_file%
    )
)

echo %comment%
git add .
git tag  "v%VERSION%" -m "%comment%"
git commit -m "%VERSION%-%comment%"

REM 执行git操作
if %PUSH_FLAG%==1 (
    git push -u origin main 
    git push origin  %tag%
    git push -u gitee main
    git push gitee  %tag%
) 
@echo off
chcp 65001 > nul
SETLOCAL

:: 设置变量
set "VENV_DIR=venv"
set "REQUIREMENTS=requirements.txt"
set "CONFIG_FILES=config.yaml,config.example.yaml"
set "TARGET_DIR=dist"

:: 检查Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo 错误：未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

:: 创建目标目录
if not exist "%TARGET_DIR%" (
    mkdir "%TARGET_DIR%"
)

:: 创建虚拟环境
echo 正在创建Python虚拟环境...
python -m venv "%VENV_DIR%"
if %ERRORLEVEL% neq 0 (
    echo 错误：创建虚拟环境失败
    pause
    exit /b 1
)

:: 激活虚拟环境并安装依赖
echo 正在安装Python依赖...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --upgrade pip
pip install -r "%REQUIREMENTS%"
if %ERRORLEVEL% neq 0 (
    echo 错误：依赖安装失败
    pause
    exit /b 1
)

:: 安装PyInstaller
echo 正在安装PyInstaller...
pip install pyinstaller
if %ERRORLEVEL% neq 0 (
    echo 错误：PyInstaller安装失败
    pause
    exit /b 1
)

:: 打包主程序
echo Building Python program to EXE...
pyinstaller --onefile --noconsole  --distpath "%TARGET_DIR%"  main.py 
if %ERRORLEVEL% neq 0 (
    echo 错误：程序打包失败
    pause
    exit /b 1
)

:: 清理临时文件
if exist "build" (
    rmdir /s /q "build"
)
if exist "__pycache__" (
    rmdir /s /q "__pycache__"
)

:: 完成
echo.
echo 构建完成！输出目录：%TARGET_DIR%
pause
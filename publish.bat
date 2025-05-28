echo off
chcp 65001
REM 读取Python配置文件中的版本号
for /f "tokens=2 delims==" %%v in ('python -c "from core.config import VERSION; print('VERSION=', VERSION)"') do set VERSION=%%v

echo 当前版本: %VERSION%
git tag  v%VERSION%
git add .
git commit -m %VERSION%
git push -u origin main 
git push origin --tags
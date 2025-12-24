FROM --platform=$BUILDPLATFORM docker.1ms.run/node:20-bookworm-slim AS ui-builder
WORKDIR /ui
COPY web_ui/package.json web_ui/yarn.lock ./
RUN corepack enable && yarn install --frozen-lockfile
COPY web_ui/ ./
RUN yarn build

FROM  --platform=$BUILDPLATFORM ghcr.io/rachelos/base-full:latest AS werss-base

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app
RUN echo "1.0.$(date +%Y%m%d.%H%M)">>docker_version.txt

# 复制后端代码
ADD ./config.example.yaml  ./config.yaml
ADD . .

# 用构建产物覆盖 static（保证容器内前端为最新）
# 保留内置静态资源（logo/default-avatar等），仅覆盖构建产物
RUN rm -rf ./static/assets ./static/index.html
COPY --from=ui-builder /ui/dist/assets/ ./static/assets/
COPY --from=ui-builder /ui/dist/index.html ./static/index.html

RUN chmod +x install.sh
RUN chmod +x start.sh

EXPOSE 8001
CMD ["bash", "start.sh"]

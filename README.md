# UY-NB-Meter

一个基于 Flask 的单文件模拟水表 API 服务器，供产品开发、接口联调和测试验收使用。当前版本支持 AES-128-GCM 请求解密与响应加密，同时保留宽松鉴权规则和首页日志页面。

## 当前行为

- 接口路径：`POST /HMWSSBAPI/PostMeterReadingData`
- 首页路径：`GET /`
- 清空历史：`GET /clear`
- Key 管理接口：
  - `POST /keys/generate`
  - `POST /keys/activate`
- 鉴权规则：
  - 未提供 `Authorization` 请求头：放行
  - 提供了 `Authorization` 且值在 `VALID_AUTH_KEYS` 中：放行
  - 只有“提供了请求头但不在白名单”时才返回 `401`
  - 上报接口和 key 管理接口都使用同一规则

## AES 协议说明

是否启用 AES 由 `AES_GCM_ENABLED` 控制。
响应是否加密由 `AES_GCM_ENCRYPT_RESPONSE` 控制。

- 当 `AES_GCM_ENABLED=false` 时：
  - 请求体按明文处理
  - 响应体直接返回明文 `OK` 或 `faile`
- 当 `AES_GCM_ENABLED=true` 时：
  - 请求体必须是 `base64(nonce + ciphertext + tag)`
  - `nonce` 固定为 12 bytes
  - 算法为 `AES-128-GCM`
  - 解密后的明文必须是十六进制文本
  - 十六进制文本解码后长度必须正好等于 `158` bytes
  - 当 `AES_GCM_ENCRYPT_RESPONSE=true` 时，响应会加密后返回
  - 当 `AES_GCM_ENCRYPT_RESPONSE=false` 时，响应会直接返回明文 `OK` 或 `faile`

固定测试 key：

- 请求解密 key：`hex:b8286d10dc8ae670189223a299b0affb`
- 响应加密 key：`hex:45e036e26c95279ee61c8f452ee35543`

如果设置了环境变量，则环境变量优先：

- `AES_GCM_KEY`
- `AES_GCM_RESPONSE_KEY`
- `AES_GCM_ENCRYPT_RESPONSE`

## 请求体验证规则

当前版本不解析业务字段，只验证协议包格式。

- 解密后文本不能为空
- 解密后文本必须全部是 hex 字符
- hex 字符数必须为偶数
- `bytes.fromhex(...)` 后长度必须正好为 `158`

失败时返回：

- HTTP `400` 或 `401`
- 响应体：`faile`

成功时返回：

- HTTP `200`
- 响应体：`OK`

## 运行环境

- Python 3.12
- Flask 3.0.3
- cryptography 45.0.7

## 启动方式

```bash
cd /home/yobai/UY-NB-Meter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

默认启动参数：

- 地址：`127.0.0.1`
- 端口：`15556`
- Debug：`True`

启动后可访问：

- 首页：`http://127.0.0.1:15556/`
- 上报接口：`http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData`

## 部署/更新脚本

仓库内提供了 Ubuntu / systemd 场景的脚本：

```bash
cd /home/yobai/UY-NB-Meter
cp .env.example .env
bash deploy/deploy_update.sh install
sudo bash deploy/deploy_update.sh install-service
```

后续更新：

```bash
cd /home/yobai/UY-NB-Meter
bash deploy/deploy_update.sh update
```

常用命令：

- `bash deploy/deploy_update.sh restart`
- `bash deploy/deploy_update.sh status`
- `bash deploy/deploy_update.sh logs`

说明：

- `install` 会创建 `.venv` 并安装 `requirements.txt`
- `update` 会先执行 `git fetch/pull --ff-only`，再更新依赖并重启 `systemd` 服务
- `refresh` 只重新安装依赖并重启服务，不执行任何 git 操作
- 若仓库存在未提交改动，`update` 会停止，避免覆盖本地修改
- 服务模板文件是 `deploy/uy-nb-meter.service.template`
- 环境变量建议写在项目根目录 `.env`

## GitHub 一键执行

如果脚本已经推到 GitHub，并且 Release 中上传了固定文件名 `UY-NB-Meter-release.tar.gz`，可以直接通过 Raw 地址执行：

```bash
curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | bash -s -- install
```

安装并自动注册 `systemd`：

```bash
curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | INSTALL_SERVICE=1 bash -s -- install
```

更新现有部署：

```bash
curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | bash -s -- update
```

可选变量：

- `TARGET_DIR=/opt/UY-NB-Meter`
- `RELEASE_TAG=v1.0.0`
- `RELEASE_URL=https://github.com/.../UY-NB-Meter-release.tar.gz`
- `SOURCE_REF=main`
- `RUN_TESTS=1`
- `INSTALL_SERVICE=1`

说明：

- `install.sh` 只下载 Release 包并解压安装，不依赖 `git`
- 如果 `latest` 或指定 tag 下没有找到 Release 资产，会自动回退到 GitHub 源码 tarball
- 如果 `TARGET_DIR` 指向 `/opt/...` 这类受限目录，脚本会自动尝试用 `sudo` 创建目录并把目录所有权交给当前用户
- 实际部署逻辑仍在 `deploy/deploy_update.sh`
- 首次执行会自动从 `.env.example` 生成 `.env`
- 更新时会保留本地 `.env` 和 `.venv`
- 如果服务器下载 PyPI 很慢，可在 `.env` 中配置大陆/海外双源回退

中国大陆服务器示例：

```bash
cat >> .env <<'EOF'
PIP_REGION=mainland
PIP_MAINLAND_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_MAINLAND_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
PIP_OVERSEAS_INDEX_URL=https://pypi.org/simple
PIP_OVERSEAS_TRUSTED_HOST=pypi.org files.pythonhosted.org
PIP_TIMEOUT=120
PIP_RETRIES=20
PIP_RESUME_RETRIES=20
EOF
```

海外服务器示例：

```bash
cat >> .env <<'EOF'
PIP_REGION=overseas
PIP_MAINLAND_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_MAINLAND_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
PIP_OVERSEAS_INDEX_URL=https://pypi.org/simple
PIP_OVERSEAS_TRUSTED_HOST=pypi.org files.pythonhosted.org
PIP_TIMEOUT=120
PIP_RETRIES=20
PIP_RESUME_RETRIES=20
EOF
```

行为说明：

- `PIP_REGION=mainland` 时，优先走清华镜像，失败后回退到官方 PyPI
- `PIP_REGION=overseas` 时，优先走官方 PyPI，失败后回退到清华镜像
- 如果显式设置了 `PIP_INDEX_URL`，则只使用该自定义源

推荐傻瓜命令：

中国大陆服务器，安装到 `/opt/UY-NB-Meter` 并注册服务：

```bash
curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | TARGET_DIR=/opt/UY-NB-Meter PIP_REGION=mainland INSTALL_SERVICE=1 bash -s -- install
```

海外服务器，安装到 `/opt/UY-NB-Meter` 并注册服务：

```bash
curl -fsSL https://raw.githubusercontent.com/yobai-cc/UY-NB-Meter/main/install.sh | TARGET_DIR=/opt/UY-NB-Meter PIP_REGION=overseas INSTALL_SERVICE=1 bash -s -- install
```

发布 Release 包：

```bash
cd /home/yobai/UY-NB-Meter
bash deploy/build_release.sh
```

然后把生成的 `UY-NB-Meter-release.tar.gz` 上传到 GitHub Release 资产中即可。

如果使用仓库内的 GitHub Actions 工作流，也可以直接打 tag 自动发布：

```bash
git tag v1.0.0
git push origin v1.0.0
```

工作流会自动构建并上传同名资产 `UY-NB-Meter-release.tar.gz`，之后安装脚本可通过 `RELEASE_TAG=v1.0.0` 下载该版本。

## AES 请求示例

下面示例会构造一个合法请求。示例明文是 `AA` 重复 `158` 次，对应 `158` bytes 协议包。

```bash
python3 - <<'PY'
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = bytes.fromhex("b8286d10dc8ae670189223a299b0affb")
nonce = b"UYNBMETER123"
plain_text = "AA" * 158

payload = AESGCM(key).encrypt(nonce, plain_text.encode("utf-8"), None)
print(base64.b64encode(nonce + payload).decode("ascii"))
PY
```

将上面输出的 base64 文本作为请求体发送：

```bash
curl -i "http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData" \
  -H "Content-Type: text/plain" \
  --data-binary "这里替换成上一步生成的 base64"
```

带白名单鉴权的示例：

```bash
curl -i "http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData" \
  -H "Authorization: Basic ZWRwOk5hdmF5dWdhMTIz" \
  -H "Content-Type: text/plain" \
  --data-binary "这里替换成上一步生成的 base64"
```

## 首页说明

首页会展示：

- 当前 AES 模式是否启用
- 当前请求 key、响应 key、key 来源
- 鉴权规则与失败原因说明
- 最近最多 50 条请求历史

日志表包含：

- `Time`
- `Result`
- `Auth`
- `Raw Body Text Length`
- `Decrypted Text Length`
- `Hex Text Length`
- `Protocol Byte Length`
- `Field Count`
- `Request Crypto`
- `Response Crypto`
- `Decode Status`
- `Error`
- `Raw Data`

## 测试与验证

如果系统 Python 缺依赖，请使用虚拟环境执行：

```bash
cd /home/yobai/UY-NB-Meter
.venv/bin/python -m unittest -v
```

## 项目限制

- 历史记录只保存在内存中，服务重启后会丢失
- 页面模板直接内嵌在 `server.py`
- 没有数据库、没有模板目录、没有额外框架

## 详细文档

详见 [开发文档.md](./开发文档.md) 和 [测试使用说明.md](./测试使用说明.md)。

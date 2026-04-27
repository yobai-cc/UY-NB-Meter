# UY-NB-Meter Ubuntu 部署文档

## 1. 文档说明

本文档用于将 `UY-NB-Meter` 部署到 Ubuntu 服务器。当前项目是一个单文件 Flask 服务，支持 AES-128-GCM 请求解密与响应加密。

已知对外地址：

- 页面：`https://hmwssbapi.bovetech.cn:15001/`
- API：`http://hmwssbapi.bovetech.cn:15000/HMWSSBAPI/PostMeterReadingData`

本地监听：

- `127.0.0.1:15556`

推荐部署方式：

1. 使用 Python 虚拟环境安装依赖
2. 使用 `systemd` 托管服务
3. 使用 `Caddy` 暴露 `15000/15001`

## 2. 推荐部署架构

```text
设备 / 浏览器
        |
        v
Caddy : 15000 / 15001
        |
        v
127.0.0.1:15556
        |
        v
UY-NB-Meter (Python / Flask)
```

## 3. 服务器准备

建议环境：

- Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
- 具有 sudo 权限的用户
- 域名已解析到服务器公网 IP

建议部署目录：

```bash
/opt/UY-NB-Meter
```

## 4. 安装基础环境

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl debian-keyring debian-archive-keyring apt-transport-https
```

安装 Caddy：

```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

## 5. 部署项目文件

```bash
sudo mkdir -p /opt/UY-NB-Meter
sudo chown -R $USER:$USER /opt/UY-NB-Meter
```

将仓库文件放到：

```bash
/opt/UY-NB-Meter
```

## 6. 创建 Python 虚拟环境

```bash
cd /opt/UY-NB-Meter
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

当前依赖：

- `Flask==3.0.3`
- `cryptography==45.0.7`

## 7. AES 环境变量

内置测试 key：

- 请求解密 key：`hex:b8286d10dc8ae670189223a299b0affb`
- 响应加密 key：`hex:45e036e26c95279ee61c8f452ee35543`

推荐显式配置环境变量，避免部署时产生误解。

例如在 `systemd` 中增加：

```ini
Environment=AES_GCM_ENABLED=true
Environment=AES_GCM_ENCRYPT_RESPONSE=true
Environment=AES_GCM_KEY=hex:b8286d10dc8ae670189223a299b0affb
Environment=AES_GCM_RESPONSE_KEY=hex:45e036e26c95279ee61c8f452ee35543
```

可选环境变量：

- `AES_GCM_ENCRYPT_RESPONSE`
- `AES_GCM_REQUEST_AAD`
- `AES_GCM_RESPONSE_AAD`
- `AES_GCM_KEY_STORE_PATH`
- `AES_GCM_ACTIVE_KEY_NAME`

## 8. 快速启动验证

```bash
cd /opt/UY-NB-Meter
source venv/bin/activate
export AES_GCM_ENABLED=true
export AES_GCM_ENCRYPT_RESPONSE=true
python server.py
```

然后本机验证：

```bash
curl http://127.0.0.1:15556/
```

如果返回 HTML 页面，说明程序已正常启动。

## 9. 使用 systemd 托管服务

创建服务文件：

```bash
sudo nano /etc/systemd/system/uy-nb-meter.service
```

写入以下内容：

```ini
[Unit]
Description=UY-NB-Meter Flask service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/UY-NB-Meter
ExecStart=/opt/UY-NB-Meter/venv/bin/python /opt/UY-NB-Meter/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=AES_GCM_ENABLED=true
Environment=AES_GCM_ENCRYPT_RESPONSE=true
Environment=AES_GCM_KEY=hex:b8286d10dc8ae670189223a299b0affb
Environment=AES_GCM_RESPONSE_KEY=hex:45e036e26c95279ee61c8f452ee35543

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable uy-nb-meter
sudo systemctl start uy-nb-meter
```

查看状态：

```bash
sudo systemctl status uy-nb-meter
sudo journalctl -u uy-nb-meter -f
```

## 10. 配置 Caddy

编辑：

```bash
sudo nano /etc/caddy/Caddyfile
```

写入：

```caddy
https://hmwssbapi.bovetech.cn:15001 {
    reverse_proxy 127.0.0.1:15556
}

http://hmwssbapi.bovetech.cn:15000 {
    handle /HMWSSBAPI* {
        reverse_proxy 127.0.0.1:15556
    }

    handle {
        redir https://hmwssbapi.bovetech.cn:15001{uri}
    }
}
```

启用配置：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 11. 防火墙配置

如果启用了 UFW：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 15000/tcp
sudo ufw allow 15001/tcp
sudo ufw enable
sudo ufw status
```

说明：

- 需要放行 `15000/tcp` 和 `15001/tcp`
- 不建议直接暴露 `15556`

## 12. 接口验证

### 12.1 页面验证

访问：

- `http://hmwssbapi.bovetech.cn:15000/`
- `https://hmwssbapi.bovetech.cn:15001/`

应看到：

- `Key Management`
- `Test Usage Guide`
- 请求日志表

### 12.2 上报接口验证

先生成请求体：

```bash
BODY="$(python3 - <<'PY'
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

key = bytes.fromhex("b8286d10dc8ae670189223a299b0affb")
nonce = b"UYNBMETER123"
plain_text = "AA" * 158

payload = AESGCM(key).encrypt(nonce, plain_text.encode("utf-8"), None)
print(base64.b64encode(nonce + payload).decode("ascii"))
PY
)"
```

发送请求：

```bash
curl -i -X POST "http://hmwssbapi.bovetech.cn:15000/HMWSSBAPI/PostMeterReadingData" \
  -H "Authorization: Basic ZWRwOk5hdmF5dWdhMTIz" \
  -H "Content-Type: text/plain" \
  --data-binary "$BODY"
```

成功时预期：

- HTTP `200`
- 返回一段 base64 文本

说明：

- 当 `AES_GCM_ENCRYPT_RESPONSE=true` 时，当前响应会被 AES-GCM 加密
- 所以不会直接返回明文 `OK`

## 13. 更新部署流程

推荐更新步骤：

1. 备份当前项目目录
2. 替换项目文件
3. 如依赖变化，重新执行 `pip install -r requirements.txt`
4. 检查 `systemd` 中的 AES 环境变量
5. 重启服务
6. 验证页面和接口

常用命令：

```bash
cd /opt/UY-NB-Meter
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart uy-nb-meter
sudo systemctl status uy-nb-meter
```

## 14. 常见问题排查

### 14.1 服务无法启动

检查：

```bash
sudo systemctl status uy-nb-meter
sudo journalctl -u uy-nb-meter -n 100 --no-pager
```

重点关注：

- Python 路径是否正确
- 工作目录是否正确
- 依赖是否已安装
- 环境变量是否设置正确

### 14.2 接口返回 401

检查：

- `Authorization` 是否填写错误
- 白名单是否仍是：
  - `Basic ZWRwOk5hdmF5dWdhMTIz`
  - `Basic YWRtaW46MTIzNDU2`

说明：

- 不带 `Authorization` 当前代码仍会放行
- 只有带了错误值才返回 `401`

### 14.3 接口返回 400

重点检查：

- 请求体是否是合法 base64
- AES key 是否匹配
- 解密后是否是 hex 文本
- hex 解码后长度是否等于 `158`

### 14.4 页面显示正常但接口测试失败

这通常说明：

- Web 页面链路正常
- 但 AES 请求体构造不正确，或者 Authorization 有误

先查看首页里的：

- `Request Crypto`
- `Decode Status`
- `Error`
- `Protocol Byte Length`

## 15. 生产建议

当前项目偏向开发测试环境。如果后续需要长期线上运行，建议补齐：

- 将 `debug=True` 改为 `debug=False`
- 将白名单改为环境变量配置
- 增加落盘日志
- 增加持久化存储
- 视需要收紧“不带 Authorization 也放行”的规则

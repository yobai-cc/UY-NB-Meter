# UY-NB-Meter Ubuntu 部署文档

## 1. 文档说明

本文档用于将 `UY-NB-Meter` 部署到 Ubuntu 服务器。

当前项目是一个单文件 Flask 服务，核心入口为：

- `server.py`

当前代码默认监听：

- `127.0.0.1:15555`

线上已知域名为：

- `https://hmwssbapi.bovetech.cn:15001/`

推荐的 Ubuntu 生产部署方式：

1. 使用 Python 虚拟环境安装依赖
2. 使用 `systemd` 托管服务
3. 使用 `Caddy` 做反向代理
4. 保持与原有端口行为一致：HTTP `15000`，HTTPS `15001`

## 2. 推荐部署架构

```text
设备 / 浏览器
        |
        v
Caddy : 15000 / 15001
        |
        v
127.0.0.1:15555
        |
        v
UY-NB-Meter (Python / Flask)
```

说明：

- Flask 服务只监听本机回环地址，不直接暴露公网端口
- Caddy 对外负责 `15000/15001` 端口访问与代理转发
- Flask 通过 `X-Forwarded-Proto` 判断请求来源是否为 HTTPS
- 为了保持用户无差异感，页面与 API 行为沿用旧规则

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

先更新系统并安装所需软件：

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

### 4.1 最短部署命令清单

如果你想按最短路径直接部署，可以按下面顺序执行：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
sudo mkdir -p /opt/UY-NB-Meter
sudo chown -R $USER:$USER /opt/UY-NB-Meter
```

然后你只需要把项目文件上传到：

```bash
/opt/UY-NB-Meter
```

## 5. 部署项目文件

将项目上传到服务器，例如：

```bash
sudo mkdir -p /opt/UY-NB-Meter
sudo chown -R $USER:$USER /opt/UY-NB-Meter
```

然后把仓库文件放到：

```bash
/opt/UY-NB-Meter
```

部署后目录示例：

```text
/opt/UY-NB-Meter
|-- server.py
|-- requirements.txt
|-- README.md
|-- 开发文档.md
|-- 部署文档.md
|-- Ubuntu部署文档.md
```

## 6. 创建 Python 虚拟环境

进入项目目录并安装依赖：

```bash
cd /opt/UY-NB-Meter
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

当前项目依赖为：

- `Flask==3.0.3`

## 7. 快速启动验证

在正式配置 systemd 前，可以先手动启动确认程序能跑起来：

```bash
cd /opt/UY-NB-Meter
source venv/bin/activate
python server.py
```

然后在服务器本机验证：

```bash
curl http://127.0.0.1:15555/
```

如果返回 HTML 页面，说明程序已正常启动。

注意：

- 当前代码使用 Flask 自带开发服务器
- 当前代码默认 `debug=True`
- 这适合联调，不建议直接作为长期生产方案

## 8. 生产启动方式建议

当前 `server.py` 最后是：

```python
app.run(debug=True, host='127.0.0.1', port=15555)
```

在 Ubuntu 生产环境，建议至少先把它改成：

```python
app.run(debug=False, host='127.0.0.1', port=15555)
```

如果暂时不改代码，也可以先部署，但不建议长期保留 `debug=True`。

## 9. 使用 systemd 托管服务

### 9.1 创建服务文件

创建：

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

[Install]
WantedBy=multi-user.target
```

说明：

- `User=www-data` 适合简单部署
- 如果你们有专门部署账号，也可以替换为独立用户
- `Restart=always` 可在进程异常退出后自动拉起

### 9.2 启用服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable uy-nb-meter
sudo systemctl start uy-nb-meter
```

### 9.3 查看服务状态

```bash
sudo systemctl status uy-nb-meter
```

### 9.4 查看日志

```bash
sudo journalctl -u uy-nb-meter -f
```

## 10. 配置 Caddy 反向代理

### 10.1 创建站点配置

创建：

```bash
sudo nano /etc/caddy/Caddyfile
```

写入以下内容：

```caddy
# ---------------------------------------------------------
# 1. HTTPS 通道 (端口 15001)
# 用途: Web 控制台 (安全登录) & 支持 SSL 的新水表
# ---------------------------------------------------------
https://hmwssbapi.bovetech.cn:15001 {
    reverse_proxy 127.0.0.1:15555
}

# ---------------------------------------------------------
# 2. HTTP 通道 (端口 15000)
# 用途: 旧水表上报 & 自动跳转
# ---------------------------------------------------------
http://hmwssbapi.bovetech.cn:15000 {
    handle /HMWSSBAPI* {
        reverse_proxy 127.0.0.1:15555
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

如果是首次部署，也建议执行：

```bash
sudo systemctl enable caddy
sudo systemctl restart caddy
```

### 10.2 访问验证

配置完成后可以验证：

```bash
curl -I http://hmwssbapi.bovetech.cn:15000/
```

如果返回 `200` 或 `301`，说明 Caddy 站点基本可用。

## 11. 配置 HTTPS

如果域名 `hmwssbapi.bovetech.cn` 已经正确解析到这台 Ubuntu 服务器，Caddy 会按 `https://hmwssbapi.bovetech.cn:15001` 这条站点规则提供 HTTPS。

通常只需要：

```bash
sudo systemctl restart caddy
```

查看 Caddy 运行状态：

```bash
sudo systemctl status caddy
```

查看证书申请或续期日志：

```bash
sudo journalctl -u caddy -f
```

## 12. 防火墙配置

如果服务器启用了 UFW，可执行：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 15000/tcp
sudo ufw allow 15001/tcp
sudo ufw enable
sudo ufw status
```

说明：

- 需要放行 `15000/tcp` 与 `15001/tcp`
- 不建议直接放行 15555，因为该端口只应供本机访问

## 13. 接口验证

### 13.1 首页验证

浏览器访问：

- `http://hmwssbapi.bovetech.cn:15000/`
- `https://hmwssbapi.bovetech.cn:15001/`

应能看到监控页面。

### 13.2 上报接口验证

可以使用下面命令测试：

```bash
curl -X POST "http://hmwssbapi.bovetech.cn:15000/HMWSSBAPI/PostMeterReadingData" \
  -H "Authorization: Basic ZWRwOk5hdmF5dWdhMTIz" \
  -H "Content-Type: text/plain" \
  --data "QBKB01,123456789,31,240101120000,1,12.34,0,240101000000,240101120000,1.23,3.654321,0,0,0,Storm"
```

成功时预期返回：

- HTTP `200`

## 14. 更新部署流程

推荐更新步骤：

1. 备份当前项目目录
2. 替换 `server.py` 或其他项目文件
3. 如依赖有变化，重新执行 `pip install -r requirements.txt`
4. 重启服务
5. 验证首页和接口

常用命令：

```bash
cd /opt/UY-NB-Meter
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart uy-nb-meter
sudo systemctl status uy-nb-meter
```

## 15. 最终可复制配置

### 15.1 `systemd` 服务文件

文件路径：

```bash
/etc/systemd/system/uy-nb-meter.service
```

完整内容：

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

[Install]
WantedBy=multi-user.target
```

### 15.2 `Caddyfile`

文件路径：

```bash
/etc/caddy/Caddyfile
```

完整内容：

```caddy
# ---------------------------------------------------------
# 1. HTTPS 通道 (端口 15001)
# 用途: Web 控制台 (安全登录) & 支持 SSL 的新水表
# ---------------------------------------------------------
https://hmwssbapi.bovetech.cn:15001 {
    reverse_proxy 127.0.0.1:15555
}

# ---------------------------------------------------------
# 2. HTTP 通道 (端口 15000)
# 用途: 旧水表上报 & 自动跳转
# ---------------------------------------------------------
http://hmwssbapi.bovetech.cn:15000 {
    handle /HMWSSBAPI* {
        reverse_proxy 127.0.0.1:15555
    }

    handle {
        redir https://hmwssbapi.bovetech.cn:15001{uri}
    }
}
```

## 16. 常见问题排查

### 16.1 服务无法启动

检查：

```bash
sudo systemctl status uy-nb-meter
sudo journalctl -u meter-demo -n 100 --no-pager
```

重点关注：

- Python 路径是否正确
- `WorkingDirectory` 是否正确
- 依赖是否安装完成
- `server.py` 是否报语法错误

### 16.2 Caddy 反向代理失败

通常表示 Caddy 没有成功连到 Flask 服务。检查：

```bash
curl http://127.0.0.1:15555/
sudo systemctl status uy-nb-meter
sudo systemctl status caddy
```

### 16.3 页面显示为 HTTP 而不是 HTTPS

检查 Caddy 是否正确传递了：

- `X-Forwarded-Proto`

因为当前代码通过这个头判断 `IsSecure`。

### 16.4 接口返回 401

检查 `Authorization` 请求头是否正确，当前白名单为：

- `Basic ZWRwOk5hdmF5dWdhMTIz`
- `Basic YWRtaW46MTIzNDU2`

### 16.5 接口返回 400

重点检查：

- 请求体是否为空
- 字段数是否为 14 或 15
- `CAN` 是否为 9 位数字
- `RSSI` 是否小于 12
- 流量、电压等字段是否能转成数值

## 17. 生产建议

为了让 Ubuntu 线上运行更稳定，建议后续继续完善：

- 将 `debug=True` 改为 `debug=False`
- 把鉴权白名单改成环境变量配置
- 增加日志文件或结构化日志
- 增加数据库持久化，避免重启丢失历史
- 将 HTML 模板从 `server.py` 中拆出

## 18. 部署结论

当前项目在 Ubuntu 上最稳妥的部署方式，是使用 `systemd + Caddy`。这套方案简单、直接，HTTPS 处理也更省心，比较适合现在这个单文件 Flask 项目。

如果你愿意，我下一步可以继续帮你把 [部署文档.md](c:\Users\ITAdministrator\Downloads\114.215.254.66\202603231109\UY-NB-Meter\部署文档.md) 也整理成“通用版 + Ubuntu版”的双入口，或者再补一份带 `Gunicorn` 的更标准生产部署文档。

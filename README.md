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

- 当 `AES_GCM_ENABLED=false` 时：
  - 请求体按明文处理
  - 响应体直接返回明文 `OK` 或 `faile`
- 当 `AES_GCM_ENABLED=true` 时：
  - 请求体必须是 `base64(nonce + ciphertext + tag)`
  - `nonce` 固定为 12 bytes
  - 算法为 `AES-128-GCM`
  - 解密后的明文必须是十六进制文本
  - 十六进制文本解码后长度必须正好等于 `158` bytes
  - 成功响应会加密后返回 `OK`
  - 失败响应会加密后返回 `faile`

固定测试 key：

- 请求解密 key：`hex:b8286d10dc8ae670189223a299b0affb`
- 响应加密 key：`hex:45e036e26c95279ee61c8f452ee35543`

如果设置了环境变量，则环境变量优先：

- `AES_GCM_KEY`
- `AES_GCM_RESPONSE_KEY`

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

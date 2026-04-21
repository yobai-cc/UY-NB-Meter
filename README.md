# UY-NB-Meter

一个基于 Flask 的单文件水表上报接收服务。当前版本保留单文件 `server.py` 和内存历史记录，只做最小化鉴权与长度校验，并提供一个请求日志页面。

## 当前行为

- 接口路径：`POST /HMWSSBAPI/PostMeterReadingData`
- 首页路径：`GET /`
- 可选清空：`GET /clear`
- 鉴权规则：
  - 未提供 `Authorization` 请求头：放行
  - 提供了 `Authorization` 且值在 `VALID_AUTH_KEYS` 中：放行
  - 只有“提供了请求头但不在白名单”时才返回 `401`
- 请求体验证规则：
  - 只按原始请求体字节长度判断
  - `len(raw_body_bytes) == 158` 时通过
  - 其他任何长度都返回 `400`
- 成功响应：
  - HTTP `200`
  - 纯文本响应体：`OK`
- 失败响应：
  - HTTP `400` 或 `401`
  - 纯文本响应体：`faile`

注意：字段数量 `Field Count` 仅用于首页展示和调试，不参与接口验收。

## 运行环境

- Python 3.12
- Flask 3.0.3

## 启动方式

```bash
cd /home/yobai/UY-NB-Meter
python3 server.py
```

默认启动参数：

- 地址：`127.0.0.1`
- 端口：`15556`
- Debug：`True`

启动后可访问：

- 首页：`http://127.0.0.1:15556/`
- 上报接口：`http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData`

## 接口示例

158 字节请求体示例：

```bash
BODY="$(printf 'A%.0s' {1..158})"
curl -i "http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData" \
  -H "Content-Type: text/plain" \
  --data-binary "$BODY"
```

带白名单鉴权的示例：

```bash
BODY="$(printf 'B%.0s' {1..158})"
curl -i "http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData" \
  -H "Authorization: Basic ZWRwOk5hdmF5dWdhMTIz" \
  -H "Content-Type: text/plain" \
  --data-binary "$BODY"
```

失败示例：

```bash
curl -i "http://127.0.0.1:15556/HMWSSBAPI/PostMeterReadingData" \
  -H "Authorization: Basic invalid" \
  -H "Content-Type: text/plain" \
  --data-binary "short"
```

## 首页说明

首页为简化后的请求日志页面，展示最近最多 50 条内存记录，列包括：

- `Time`
- `Result`
- `Auth`
- `Body Length`
- `Field Count`
- `Error`
- `Raw Data`

## 项目限制

- 历史记录只保存在内存中，服务重启后会丢失
- 页面模板直接内嵌在 `server.py`
- 没有数据库、没有模板目录、没有额外框架

## 详细文档

详见 [开发文档.md](./开发文档.md)。

"""轻量签名会话令牌 (itsdangerous 风格, 无额外依赖)。

令牌形如 ``base64(payload).base64(signature)``; 服务端无需存表,
重启/多 worker 之间凭 SECRET_KEY 即可互验。
"""
import base64
import hashlib
import hmac
import json

from flask import current_app


def _sign(payload_b64):
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def _b64encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text):
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def make_token(payload):
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_b64)
    return "%s.%s" % (payload_b64, signature)


def read_token(token):
    """验证签名并解析 payload; 失败/伪造返回 None。"""
    if not token or "." not in token:
        return None
    payload_b64, _, signature = token.partition(".")
    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        return json.loads(_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

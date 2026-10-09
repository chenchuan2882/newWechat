"""Server-side WeChat authentication and fail-closed content moderation."""

import threading
import time
import requests
from flask import current_app

_lock = threading.Lock()
_token = {"value": "", "expires": 0, "appid": ""}


class WechatError(Exception):
    pass


def credentials():
    appid = current_app.config["WECHAT_APPID"]
    secret = current_app.config["WECHAT_APPSECRET"]
    if not secret:
        raise WechatError("微信服务尚未配置，请联系管理员")
    return appid, secret


def login(code):
    appid, secret = credentials()
    data = requests.get(
        "https://api.weixin.qq.com/sns/jscode2session",
        params={
            "appid": appid,
            "secret": secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    ).json()
    if not data.get("openid") or data.get("errcode"):
        raise WechatError("登录失败，请重新登录")
    return data["openid"]


def access_token():
    appid, secret = credentials()
    with _lock:
        if _token["appid"] == appid and _token["expires"] > time.time():
            return _token["value"]
        data = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": appid,
                "secret": secret,
            },
            timeout=10,
        ).json()
        if not data.get("access_token"):
            raise WechatError("内容审核服务暂不可用，请稍后再试")
        _token.update(
            value=data["access_token"],
            appid=appid,
            expires=time.time() + max(0, data.get("expires_in", 7200) - 120),
        )
        return _token["value"]


def check_text(content, openid, scene=3):
    data = requests.post(
        "https://api.weixin.qq.com/wxa/msg_sec_check",
        params={"access_token": access_token()},
        json={"version": 2, "openid": openid, "scene": scene, "content": content},
        timeout=10,
    ).json()
    if data.get("errcode") == 87014 or data.get("result", {}).get("suggest") in (
        "risky",
        "review",
    ):
        raise WechatError("内容包含不当信息，请修改后重试")
    if data.get("errcode", -1) != 0 or data.get("result", {}).get("suggest") != "pass":
        raise WechatError("内容审核未通过，请稍后再试")


def check_image(content):
    data = requests.post(
        "https://api.weixin.qq.com/wxa/img_sec_check",
        params={"access_token": access_token()},
        files={"media": ("image.jpg", content, "image/jpeg")},
        timeout=15,
    ).json()
    if data.get("errcode") == 87014:
        raise WechatError("图片包含不当信息，请更换后重试")
    if data.get("errcode", -1) != 0:
        raise WechatError("图片审核未通过，请稍后再试")

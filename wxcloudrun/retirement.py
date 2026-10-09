import base64
import binascii
import io
import json
import secrets
import random
import re
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from flask import Blueprint, current_app, g, jsonify, request, send_file
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from wxcloudrun import db
from wxcloudrun.retirement_models import (
    User,
    Post,
    Wish,
    BlueprintItem,
    Comment,
    Reaction,
    Report,
    Milestone,
    Media,
    Notification,
    PostDimension,
    HotSnapshot,
    Subscription,
)
from wxcloudrun import wechat

api = Blueprint("retirement", __name__, url_prefix="/api")
DIMENSIONS = ["location", "daily", "social", "finance", "health"]
DIMENSION_NAMES = ["住在哪", "每天做什么", "和谁在一起", "财务准备", "健康管理"]
SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_SETTINGS = {
    "milestone": True,
    "annual": True,
    "collection": True,
    "comment": True,
    "wish": False,
}


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


@api.errorhandler(ApiError)
def handle_api_error(error):
    db.session.rollback()
    return jsonify(code=-1, errorMsg=error.message), error.status


@api.errorhandler(wechat.WechatError)
def handle_wechat_error(error):
    db.session.rollback()
    return jsonify(code=-1, errorMsg=str(error)), 503


@api.errorhandler(Exception)
def handle_error(error):
    db.session.rollback()
    if isinstance(error, HTTPException):
        return jsonify(code=-1, errorMsg=error.description), error.code
    if isinstance(error, (requests.RequestException, ValueError)):
        return jsonify(code=-1, errorMsg="服务暂不可用，请稍后再试"), 503
    current_app.logger.exception("API request failed")
    return jsonify(code=-1, errorMsg="服务异常，请稍后再试"), 500


def ok(data=None):
    return jsonify(code=0, data=data if data is not None else {})


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError("请求体必须为 JSON 对象")
    return value


def text(value, label, low, high):
    if not isinstance(value, str) or not low <= len(value.strip()) <= high:
        raise ApiError("{}需为{}-{}字".format(label, low, high))
    return value.strip()


def number(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ApiError("{}超出范围".format(label))
    return value


def dimension(value, optional=False):
    if optional and value in ("", None):
        return None
    if value not in DIMENSIONS:
        raise ApiError("请选择有效维度")
    return value


def tags(value, count=5):
    if not isinstance(value, list) or len(value) > count:
        raise ApiError("标签最多{}个".format(count))
    return list(dict.fromkeys(text(x, "标签", 1, 8) for x in value))


def serializer():
    if not current_app.config["SECRET_KEY"]:
        raise ApiError("登录服务尚未配置，请联系管理员", 503)
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt="retirement-session-v1"
    )


@api.before_request
def identify():
    g.user = None
    token = request.headers.get("Authorization", "")
    if not token.startswith("Bearer "):
        return
    try:
        user_id = serializer().loads(
            token[7:], max_age=current_app.config["SESSION_MAX_AGE"]
        )
        g.user = db.session.get(User, user_id)
    except (BadSignature, SignatureExpired):
        pass


def authenticated(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not g.user:
            raise ApiError("请先登录", 401)
        return fn(*args, **kwargs)

    return inner


def lock_user():
    # Serialize quota-sensitive writes across workers, including MySQL.
    return (
        User.query.filter_by(id=g.user.id).populate_existing().with_for_update().one()
    )


def page_args(limit=20):
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        raise ApiError("页码无效")
    if page > 10000:
        raise ApiError("页码超出范围")
    return page, limit


def paginated(query, converter, limit=20):
    page, limit = page_args(limit)
    rows = query.offset((page - 1) * limit).limit(limit + 1).all()
    return {
        "items": [converter(x) for x in rows[:limit]],
        "page": page,
        "has_more": len(rows) > limit,
    }


def timestamp(value):
    return value.isoformat(timespec="seconds") + "Z"


def notify(user_id, setting, message):
    user = db.session.get(User, user_id)
    if (
        user
        and user.id != g.user.id
        and user.settings.get(setting, DEFAULT_SETTINGS[setting])
    ):
        db.session.add(Notification(user_id=user_id, text=message, kind=setting))


def public_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return {"id": user_id, "nickname": "已注销用户", "avatar_url": ""}
    profile = user.profile
    return {
        key: profile.get(key, "")
        for key in ("nickname", "avatar_url", "city", "bio", "is_retired")
    } | {"id": user.id, "retirement": retirement(profile)}


def retirement(profile, now=None):
    now = now or datetime.now(SHANGHAI)
    if not profile.get("birth_year"):
        return None
    year = profile["birth_year"] + profile["expected_retire_age"]
    # Birth month is optional; January is the documented approximation.
    month = profile.get("birth_month") or 1
    remaining = (year - now.year) * 12 + month - now.month
    elapsed = max(0, -remaining)
    retired = bool(profile.get("is_retired"))
    months = elapsed if retired else max(0, remaining)
    return {
        "year": year,
        "month": month,
        "years": months // 12,
        "months": months % 12,
        "remaining_months": remaining,
        "is_retired": retired,
        "approximate": not bool(profile.get("birth_month")),
    }


def profile_data(user):
    return {
        "id": user.id,
        **user.profile,
        "retirement": retirement(user.profile),
        "settings": {**DEFAULT_SETTINGS, **user.settings},
    }


def blueprint_data(item):
    source = db.session.get(Post, item.source_post_id) if item.source_post_id else None
    return {
        "id": item.id,
        "dimension": item.dimension,
        "content": item.content,
        "tags": item.tags,
        "source_type": item.source_type,
        "source_post_id": item.source_post_id,
        "source_author": item.source_author,
        "source_deleted": bool(
            item.source_post_id and (not source or source.status != "published")
        ),
        "created_at": timestamp(item.created_at),
        "updated_at": timestamp(item.updated_at),
    }


def reaction_count(kind, target_id):
    return Reaction.query.filter_by(kind=kind, target_id=target_id).count()


def reacted(kind, target_id):
    return bool(g.user and db.session.get(Reaction, (g.user.id, kind, target_id)))


def post_data(post):
    collected = (
        BlueprintItem.query.filter_by(user_id=g.user.id, source_post_id=post.id).first()
        if g.user
        else None
    )
    return {
        "id": post.id,
        **post.payload,
        "author": public_user(post.user_id),
        "mine": bool(g.user and post.user_id == g.user.id),
        "status": post.status,
        "like_count": reaction_count("post", post.id),
        "liked": reacted("post", post.id),
        "comment_count": Comment.query.filter_by(post_id=post.id).count(),
        "collect_count": BlueprintItem.query.filter_by(source_post_id=post.id).count(),
        "collected_dimension": collected.dimension if collected else None,
        "created_at": timestamp(post.created_at),
    }


def wish_data(wish):
    return {
        "id": wish.id,
        "content": wish.content,
        "dimension": wish.dimension,
        "author": public_user(wish.user_id),
        "liked": reacted("wish", wish.id),
        "like_count": reaction_count("wish", wish.id),
        "mine": bool(g.user and g.user.id == wish.user_id),
        "created_at": timestamp(wish.created_at),
    }


def comment_data(comment):
    return {
        "id": comment.id,
        "content": comment.content,
        "parent_id": comment.parent_id,
        "author": public_user(comment.user_id),
        "like_count": reaction_count("comment", comment.id),
        "liked": reacted("comment", comment.id),
        "created_at": timestamp(comment.created_at),
    }


def published(model, target_id, lock=False):
    query = model.query.filter_by(id=target_id, status="published")
    obj = (query.with_for_update() if lock else query).first()
    if not obj:
        raise ApiError("内容不存在或已下线", 404)
    return obj


def owned(model, target_id):
    obj = db.session.get(model, target_id)
    if not obj or obj.user_id != g.user.id:
        raise ApiError("记录不存在", 404)
    return obj


@api.get("/health")
def health():
    return ok({"status": "ok", "version": "retirement-mvp-1"})


@api.post("/user/login")
def login():
    code = text(body().get("code"), "登录凭证", 1, 256)
    signer = serializer()
    openid = wechat.login(code)
    user = User.query.filter_by(openid=openid).first()
    if not user:
        user = User(openid=openid, profile={}, settings={})
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            user = User.query.filter_by(openid=openid).one()
    return ok({"token": signer.dumps(user.id), "profile": profile_data(user)})


@api.route("/user/profile", methods=["GET", "PUT"])
@authenticated
def profile():
    if request.method == "GET":
        return ok(profile_data(g.user))
    value = body()
    nickname = text(value.get("nickname"), "昵称", 2, 16)
    if not re.fullmatch(r"[\w\u4e00-\u9fff ·.-]+", nickname):
        raise ApiError("昵称包含不支持的字符")
    birth = number(value.get("birth_year"), "出生年份", 1950, 2000)
    age = number(value.get("expected_retire_age"), "退休年龄", 45, 70)
    retired = value.get("is_retired", False)
    if type(retired) is not bool:
        raise ApiError("退休状态无效")
    if not retired and age <= datetime.now(SHANGHAI).year - birth:
        raise ApiError("退休年龄需大于当前年龄")
    if retired and birth + age > datetime.now(SHANGHAI).year:
        raise ApiError("已退休用户的退休年份不能晚于当前年份")
    month = value.get("birth_month") or None
    if month is not None:
        month = number(month, "出生月份", 1, 12)
    city = value.get("city", "")
    bio = value.get("bio", "")
    if (
        not isinstance(city, str)
        or len(city) > 40
        or not isinstance(bio, str)
        or len(bio) > 30
    ):
        raise ApiError("城市或简介过长")
    avatar = value.get("avatar_url", "")
    if not isinstance(avatar, str):
        raise ApiError("头像无效")
    validate_media([avatar] if avatar else [])
    wechat.check_text(" ".join([nickname, city, bio]), g.user.openid, scene=1)
    g.user.profile = {
        "nickname": nickname,
        "birth_year": birth,
        "birth_month": month,
        "expected_retire_age": age,
        "is_retired": retired,
        "city": city,
        "bio": bio,
        "avatar_url": avatar,
    }
    db.session.commit()
    return ok(profile_data(g.user))


@api.put("/user/settings")
@authenticated
def settings():
    value = body()
    if any(k not in DEFAULT_SETTINGS or type(v) is not bool for k, v in value.items()):
        raise ApiError("通知设置无效")
    g.user.settings = {**g.user.settings, **value}
    db.session.commit()
    return ok({**DEFAULT_SETTINGS, **g.user.settings})


@api.get("/users/<user_id>")
def author(user_id):
    if not db.session.get(User, user_id):
        raise ApiError("用户不存在", 404)
    post_count = Post.query.filter_by(user_id=user_id, status="published").count()
    wish_count = Wish.query.filter_by(user_id=user_id, status="published").count()
    collections = (
        BlueprintItem.query.join(Post, BlueprintItem.source_post_id == Post.id)
        .filter(Post.user_id == user_id)
        .count()
    )
    return ok(
        {
            "profile": {
                **public_user(user_id),
                "post_count": post_count,
                "wish_count": wish_count,
                "received_collections": collections,
            },
            "posts": [
                post_data(p)
                for p in Post.query.filter_by(user_id=user_id, status="published")
                .order_by(Post.created_at.desc())
                .limit(20)
            ],
            "wishes": [
                wish_data(w)
                for w in Wish.query.filter_by(user_id=user_id, status="published")
                .order_by(Wish.created_at.desc())
                .limit(20)
            ],
        }
    )


@api.get("/blueprint/list")
@authenticated
def blueprints():
    query = BlueprintItem.query.filter_by(user_id=g.user.id)
    dim = request.args.get("dimension")
    if dim:
        query = query.filter_by(dimension=dimension(dim))
    if request.args.get("collected") == "1":
        query = query.filter_by(source_type="collected")
    return ok(
        paginated(
            query.order_by(BlueprintItem.created_at.desc(), BlueprintItem.id.desc()),
            blueprint_data,
            50,
        )
    )


@api.post("/blueprint/item")
@authenticated
def add_blueprint():
    value = body()
    item = BlueprintItem(
        user_id=g.user.id,
        dimension=dimension(value.get("dimension")),
        content=text(value.get("content"), "想法", 1, 200),
        tags=tags(value.get("tags", [])),
    )
    db.session.add(item)
    db.session.commit()
    return ok(blueprint_data(item))


@api.route("/blueprint/item/<item_id>", methods=["PUT", "DELETE"])
@authenticated
def edit_blueprint(item_id):
    item = owned(BlueprintItem, item_id)
    if request.method == "DELETE":
        db.session.delete(item)
    else:
        value = body()
        item.content = text(value.get("content"), "想法", 1, 200)
        item.dimension = dimension(value.get("dimension", item.dimension))
        item.tags = tags(value.get("tags", []))
        item.updated_at = datetime.utcnow()
    db.session.commit()
    return ok()


@api.get("/home")
def home():
    cutoff = datetime.utcnow() - timedelta(hours=48)
    posts = (
        Post.query.filter(Post.status == "published", Post.created_at >= cutoff)
        .order_by(Post.created_at.desc())
        .limit(100)
        .all()
    )
    result = {
        "recommendations": [
            post_data(p) for p in random.sample(posts, min(2, len(posts)))
        ]
    }
    if not g.user:
        return ok(result)
    items = BlueprintItem.query.filter_by(user_id=g.user.id).all()
    counts = {d: sum(x.dimension == d for x in items) for d in DIMENSIONS}
    result.update(
        profile=profile_data(g.user),
        counts=counts,
        total=len(items),
        complete=sum(v > 0 for v in counts.values()),
        latest=(
            blueprint_data(max(items, key=lambda x: x.created_at)) if items else None
        ),
    )
    r = retirement(g.user.profile)
    result["milestone"] = None
    if r and not r["is_retired"] and g.user.settings.get("milestone", True):
        lock_user()
        previous = g.user.settings.get("last_remaining_months")
        pending = g.user.settings.get("pending_milestone")
        remaining = r["remaining_months"]
        crossed = [
            n
            for n in (10, 5, 3, 1)
            if remaining <= n * 12 and (previous is None or previous > n * 12)
        ]
        if crossed:
            # New users see only the nearest milestone, not all past ones.
            n = min(crossed)
            if not db.session.get(Milestone, (g.user.id, str(n))):
                result["milestone"] = {"kind": str(n), "years": n}
        if pending and not db.session.get(Milestone, (g.user.id, pending)):
            result["milestone"] = {"kind": pending, "years": int(pending)}
        g.user.settings = {
            **g.user.settings,
            "last_remaining_months": remaining,
            "pending_milestone": (
                result["milestone"]["kind"] if result["milestone"] else None
            ),
        }
    now = datetime.now(SHANGHAI)
    annual_kind = "annual-{}".format(now.year)
    month = g.user.profile.get("birth_month")
    if (
        month == now.month
        and g.user.settings.get("annual", True)
        and not db.session.get(Milestone, (g.user.id, annual_kind))
    ):
        recent = [
            i for i in items if i.created_at >= datetime.utcnow() - timedelta(days=365)
        ]
        result["annual"] = {
            "kind": annual_kind,
            "added": len(recent),
            "collected": sum(i.source_type == "collected" for i in recent),
            "missing": [d for d, c in counts.items() if c == 0],
        }
    db.session.commit()
    return ok(result)


@api.post("/milestones/<kind>/ack")
@authenticated
def acknowledge(kind):
    if kind not in (
        "10",
        "5",
        "3",
        "1",
        "annual-{}".format(datetime.now(SHANGHAI).year),
    ):
        raise ApiError("里程碑无效")
    lock_user()
    if not db.session.get(Milestone, (g.user.id, kind)):
        db.session.add(Milestone(user_id=g.user.id, kind=kind))
    if g.user.settings.get("pending_milestone") == kind:
        g.user.settings = {**g.user.settings, "pending_milestone": None}
    db.session.commit()
    return ok()


def validate_media(images):
    if not isinstance(images, list) or len(images) > 3:
        raise ApiError("最多上传3张图片")
    for url in images:
        if not isinstance(url, str) or not re.fullmatch(
            r"/api/media/[a-f0-9]{32}", url
        ):
            raise ApiError("图片无效，请重新上传")
        asset = db.session.get(Media, url.rsplit("/", 1)[1])
        if not asset or asset.user_id != g.user.id:
            raise ApiError("图片无效，请重新上传")


def post_payload(value):
    content = text(value.get("content"), "正文", 10, 500)
    dims = value.get("dimensions")
    if (
        not isinstance(dims, list)
        or not 1 <= len(dims) <= 3
        or any(not isinstance(d, str) for d in dims)
        or len(set(dims)) != len(dims)
    ):
        raise ApiError("请选择1-3个维度")
    dims = [dimension(d) for d in dims]
    custom = tags(value.get("custom_tags", []), 3)
    expense = value.get("expense_note", "")
    if not isinstance(expense, str) or len(expense) > 30:
        raise ApiError("花费参考最多30字")
    images = value.get("images", [])
    validate_media(images)
    wechat.check_text(" ".join([content, expense] + custom), g.user.openid)
    return {
        "content": content,
        "dimensions": dims,
        "custom_tags": custom,
        "expense_note": expense,
        "images": images,
    }


@api.get("/posts")
def posts():
    query = Post.query
    if request.args.get("mine") == "1":
        if not g.user:
            raise ApiError("请先登录", 401)
        status = request.args.get("status", "published")
        if status not in ("published", "rejected", "pending"):
            raise ApiError("状态无效")
        query = query.filter_by(user_id=g.user.id, status=status)
    else:
        query = query.filter_by(status="published")
    if request.args.get("author"):
        query = query.filter_by(user_id=request.args["author"])
    dim = request.args.get("dimension")
    if dim:
        dim = dimension(dim)
        query = query.join(PostDimension, PostDimension.post_id == Post.id).filter(
            PostDimension.dimension == dim
        )
    return ok(
        paginated(query.order_by(Post.created_at.desc(), Post.id.desc()), post_data)
    )


@api.post("/posts")
@authenticated
def publish():
    if not g.user.profile.get("nickname"):
        raise ApiError("请先完善资料")
    post = Post(user_id=g.user.id, payload=post_payload(body()))
    db.session.add(post)
    db.session.flush()
    for dim in post.payload["dimensions"]:
        db.session.add(PostDimension(post_id=post.id, dimension=dim))
    db.session.commit()
    return ok(post_data(post))


@api.route("/posts/<post_id>", methods=["GET", "PUT", "DELETE"])
def post_detail(post_id):
    if request.method == "GET":
        return ok(post_data(published(Post, post_id)))
    if not g.user:
        raise ApiError("请先登录", 401)
    post = owned(Post, post_id)
    if post.status == "deleted":
        raise ApiError("内容已删除", 404)
    if request.method == "DELETE":
        post.status = "deleted"
    else:
        post.payload = post_payload(body())
        post.status = "published"
        PostDimension.query.filter_by(post_id=post.id).delete()
        for dim in post.payload["dimensions"]:
            db.session.add(PostDimension(post_id=post.id, dimension=dim))
    post.updated_at = datetime.utcnow()
    db.session.commit()
    return ok()


@api.post("/posts/<post_id>/collect")
@authenticated
def collect(post_id):
    dim = dimension(body().get("dimension"))
    lock_user()
    post = published(Post, post_id, lock=True)
    item = BlueprintItem.query.filter_by(
        user_id=g.user.id, source_post_id=post_id
    ).first()
    if not item:
        item = BlueprintItem(
            user_id=g.user.id,
            dimension=dim,
            content=post.payload["content"][:200],
            tags=post.payload["custom_tags"],
            source_type="collected",
            source_post_id=post.id,
            source_author=public_user(post.user_id)["nickname"],
        )
        db.session.add(item)
        notify(post.user_id, "collection", "有人将你的生活分享加入了退休蓝图")
    db.session.commit()
    return ok(blueprint_data(item))


@api.post("/<kind>/<target_id>/like")
@authenticated
def like(kind, target_id):
    models = {
        "posts": (Post, "post"),
        "wishes": (Wish, "wish"),
        "comments": (Comment, "comment"),
    }
    if kind not in models:
        raise ApiError("互动类型无效", 404)
    model, reaction_kind = models[kind]
    # Desired-state writes are idempotent, preventing retries from toggling twice.
    desired = body().get("liked")
    if type(desired) is not bool:
        raise ApiError("liked 必须为布尔值")
    lock_user()
    if model is Comment:
        target = db.session.get(Comment, target_id)
        if not target:
            raise ApiError("评论不存在", 404)
        published(Post, target.post_id, lock=True)
    else:
        target = published(model, target_id, lock=True)
    reaction = db.session.get(Reaction, (g.user.id, reaction_kind, target_id))
    if desired and not reaction:
        db.session.add(
            Reaction(user_id=g.user.id, kind=reaction_kind, target_id=target_id)
        )
        if model is Wish:
            notify(target.user_id, "wish", "有人也想实现你的退休愿望")
    elif not desired and reaction:
        db.session.delete(reaction)
    db.session.commit()
    return ok(
        {"liked": desired, "like_count": reaction_count(reaction_kind, target_id)}
    )


@api.route("/posts/<post_id>/comments", methods=["GET", "POST"])
def comments(post_id):
    post = published(Post, post_id)
    if request.method == "GET":
        query = Comment.query.filter_by(post_id=post_id)
        if request.args.get("preview") == "1":
            count = (
                db.session.query(db.func.count(Reaction.target_id))
                .filter(Reaction.kind == "comment", Reaction.target_id == Comment.id)
                .correlate(Comment)
                .scalar_subquery()
            )
            return ok(
                paginated(
                    query.filter(Comment.parent_id.is_(None)).order_by(
                        count.desc(), Comment.created_at.desc(), Comment.id.desc()
                    ),
                    comment_data,
                    3,
                )
            )
        return ok(
            paginated(
                query.order_by(Comment.created_at.desc(), Comment.id.desc()),
                comment_data,
            )
        )
    if not g.user:
        raise ApiError("请先登录", 401)
    value = body()
    content = text(value.get("content"), "评论", 1, 200)
    parent_id = value.get("parent_id") or None
    if parent_id:
        parent = db.session.get(Comment, parent_id)
        if not parent or parent.post_id != post_id or parent.parent_id:
            raise ApiError("仅支持回复一级评论")
    wechat.check_text(content, g.user.openid, scene=2)
    comment = Comment(
        user_id=g.user.id, post_id=post_id, content=content, parent_id=parent_id
    )
    db.session.add(comment)
    notify(post.user_id, "comment", "你的生活分享收到一条新评论")
    if parent_id and parent.user_id != post.user_id:
        notify(parent.user_id, "comment", "你的评论收到一条回复")
    db.session.commit()
    return ok(comment_data(comment))


@api.post("/posts/<post_id>/report")
@authenticated
def report(post_id):
    reason = body().get("reason")
    if reason not in ("内容不实或误导", "广告或营销内容", "不雅或令人不适", "其他"):
        raise ApiError("请选择举报原因")
    lock_user()
    post = published(Post, post_id, lock=True)
    if not db.session.get(Report, (g.user.id, post_id)):
        db.session.add(Report(user_id=g.user.id, post_id=post_id, reason=reason))
        db.session.flush()
        if Report.query.filter_by(post_id=post_id).count() >= 5:
            post.status = "rejected"
            db.session.add(
                Notification(
                    user_id=post.user_id,
                    text="你的生活分享因多位用户举报暂时下线，请修改后重新提交",
                )
            )
    db.session.commit()
    return ok()


def hot_ids(force=False):
    snapshot = db.session.get(HotSnapshot, "global")
    now = datetime.utcnow()
    if snapshot and not force and now - snapshot.updated_at < timedelta(hours=1):
        return snapshot.ids
    count = (
        db.session.query(db.func.count(Reaction.target_id))
        .filter(Reaction.kind == "wish", Reaction.target_id == Wish.id)
        .correlate(Wish)
        .scalar_subquery()
    )
    ids = [
        w.id
        for w in Wish.query.filter_by(status="published")
        .order_by(count.desc(), Wish.created_at.desc(), Wish.id.desc())
        .limit(100)
    ]
    if not snapshot:
        snapshot = HotSnapshot(id="global", ids=ids, updated_at=now)
        db.session.add(snapshot)
    else:
        snapshot.ids, snapshot.updated_at = ids, now
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return db.session.get(HotSnapshot, "global").ids
    return ids


@api.get("/wishes")
def wishes():
    query = Wish.query.filter_by(status="published")
    if request.args.get("mine") == "1":
        if not g.user:
            raise ApiError("请先登录", 401)
        query = query.filter_by(user_id=g.user.id)
    if request.args.get("author"):
        query = query.filter_by(user_id=request.args["author"])
    if request.args.get("dimension"):
        query = query.filter_by(dimension=dimension(request.args["dimension"]))
    if request.args.get("sort", "latest") == "hot":
        ids = hot_ids()
        # Preserve the hourly global ranking; filters narrow it without resorting.
        allowed = {w.id: w for w in query.filter(Wish.id.in_(ids)).all()}
        rows = [allowed[i] for i in ids if i in allowed]
        page, limit = page_args()
        start = (page - 1) * limit
        return ok(
            {
                "items": [wish_data(w) for w in rows[start : start + limit]],
                "page": page,
                "has_more": start + limit < len(rows),
            }
        )
    return ok(
        paginated(query.order_by(Wish.created_at.desc(), Wish.id.desc()), wish_data)
    )


def today_start():
    local = datetime.now(SHANGHAI).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


@api.get("/wishes/quota")
@authenticated
def quota():
    used = Wish.query.filter(
        Wish.user_id == g.user.id, Wish.created_at >= today_start()
    ).count()
    return ok({"used": used, "remaining": max(0, 3 - used)})


@api.post("/wishes")
@authenticated
def add_wish():
    value = body()
    content = text(value.get("content"), "愿望", 10, 80)
    dim = dimension(value.get("dimension"), optional=True)
    if not g.user.profile.get("nickname"):
        raise ApiError("请先完善资料")
    wechat.check_text(content, g.user.openid)
    lock_user()
    used = Wish.query.filter(
        Wish.user_id == g.user.id, Wish.created_at >= today_start()
    ).count()
    if used >= 3:
        raise ApiError("今日已写下3个愿望，明天再来", 429)
    wish = Wish(user_id=g.user.id, content=content, dimension=dim)
    db.session.add(wish)
    db.session.commit()
    return ok(wish_data(wish))


@api.delete("/wishes/<wish_id>")
@authenticated
def delete_wish(wish_id):
    wish = owned(Wish, wish_id)
    wish.status = "deleted"
    db.session.commit()
    return ok()


@api.get("/wishes/<wish_id>/people")
def wish_people(wish_id):
    published(Wish, wish_id)
    rows = (
        Reaction.query.filter_by(kind="wish", target_id=wish_id)
        .order_by(Reaction.created_at.desc())
        .limit(5)
    )
    return ok(
        {
            "people": [public_user(row.user_id) for row in rows],
            "count": reaction_count("wish", wish_id),
        }
    )


@api.post("/media")
@authenticated
def upload_media():
    raw = body().get("base64")
    if not isinstance(raw, str) or len(raw) > 1100000:
        raise ApiError("图片需压缩至800KB以内")
    try:
        content = base64.b64decode(raw, validate=True)
        if len(content) > 800 * 1024:
            raise ApiError("图片需压缩至800KB以内")
        with Image.open(io.BytesIO(content)) as im:
            if im.width * im.height > 16000000:
                raise ApiError("图片尺寸过大")
            im.load()
            im = im.convert("RGB")
            im.thumbnail((1600, 1600))
            output = io.BytesIO()
            im.save(output, "JPEG", quality=82)
            content = output.getvalue()
    except (
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ):
        raise ApiError("图片格式无效")
    if len(content) > 800 * 1024:
        raise ApiError("图片需进一步压缩")
    wechat.check_image(content)
    media = Media(user_id=g.user.id, content=content)
    db.session.add(media)
    db.session.commit()
    return ok({"url": "/api/media/" + media.id})


@api.get("/media/<media_id>")
def media_file(media_id):
    media = db.session.get(Media, media_id)
    if not media:
        raise ApiError("图片不存在", 404)
    return send_file(io.BytesIO(media.content), mimetype=media.mime, max_age=86400)


@api.route("/notifications", methods=["GET", "PUT"])
@authenticated
def notifications():
    query = Notification.query.filter_by(user_id=g.user.id)
    if request.method == "PUT":
        query.update({"read": True})
        db.session.commit()
        return ok()
    return ok(
        paginated(
            query.order_by(Notification.created_at.desc()),
            lambda n: {
                "id": n.id,
                "text": n.text,
                "read": n.read,
                "created_at": timestamp(n.created_at),
            },
        )
    )


def subscription_templates():
    try:
        value = json.loads(current_app.config.get("SUBSCRIPTION_TEMPLATES_JSON", "{}"))
        if not isinstance(value, dict):
            raise ValueError()
        return {
            kind: spec
            for kind, spec in value.items()
            if kind in DEFAULT_SETTINGS
            and isinstance(spec, dict)
            and isinstance(spec.get("template_id"), str)
            and isinstance(spec.get("data"), dict)
        }
    except ValueError:
        raise ApiError("订阅消息配置无效", 503)


@api.get("/config")
def public_config():
    return ok(
        {
            "subscription_templates": {
                k: v["template_id"] for k, v in subscription_templates().items()
            }
        }
    )


@api.post("/user/subscriptions")
@authenticated
def consent_subscription():
    value = body()
    kind = value.get("kind")
    spec = subscription_templates().get(kind) if isinstance(kind, str) else None
    if not spec or value.get("template_id") != spec["template_id"]:
        raise ApiError("订阅模板未配置")
    lock_user()
    sub = db.session.get(Subscription, (g.user.id, kind))
    if not sub:
        sub = Subscription(
            user_id=g.user.id, kind=kind, template_id=spec["template_id"], credits=0
        )
        db.session.add(sub)
    if sub.template_id != spec["template_id"]:
        sub.template_id, sub.credits = spec["template_id"], 0
    # WeChat validates the real subscription grant at send time; this records intent only.
    sub.credits = min(100, sub.credits + 1)
    db.session.commit()
    return ok()


def schedule_reminders():
    now = datetime.now(SHANGHAI)
    for user in User.query.all():
        r = retirement(user.profile, now)
        if not r:
            continue
        user = (
            User.query.filter_by(id=user.id).populate_existing().with_for_update().one()
        )
        settings = user.settings
        if (
            settings.get("annual", True)
            and user.profile.get("birth_month") == now.month
            and now.day == 1
        ):
            kind = "annual-{}".format(now.year)
            if not db.session.get(Milestone, (user.id, "notice-" + kind)):
                db.session.add(Milestone(user_id=user.id, kind="notice-" + kind))
                db.session.add(
                    Notification(
                        user_id=user.id,
                        kind="annual",
                        text="又过了一年，来看看你的退休蓝图今年有哪些变化",
                    )
                )
        if not r["is_retired"] and settings.get("milestone", True):
            previous = settings.get("job_remaining_months")
            crossed = [
                n
                for n in (10, 5, 3, 1)
                if r["remaining_months"] <= n * 12
                and (previous is None or previous > n * 12)
            ]
            if crossed:
                n = min(crossed)
                marker = "notice-" + str(n)
                if not db.session.get(Milestone, (user.id, marker)):
                    db.session.add(Milestone(user_id=user.id, kind=marker))
                    db.session.add(
                        Notification(
                            user_id=user.id,
                            kind="milestone",
                            text="距离退休还有{}年，来完善你的人生后半程蓝图".format(n),
                        )
                    )
            user.settings = {**settings, "job_remaining_months": r["remaining_months"]}
        db.session.commit()


def dispatch_notifications():
    templates = subscription_templates()
    sent, failed = 0, 0
    ids = [
        n.id
        for n in Notification.query.filter_by(delivered=False, delivery_error=None)
        .order_by(Notification.created_at)
        .limit(100)
    ]
    for notice_id in ids:
        notice = (
            Notification.query.filter_by(id=notice_id)
            .populate_existing()
            .with_for_update()
            .one()
        )
        if notice.delivered or notice.delivery_error:
            db.session.rollback()
            continue
        sub = (
            Subscription.query.filter_by(user_id=notice.user_id, kind=notice.kind)
            .with_for_update()
            .first()
        )
        user = db.session.get(User, notice.user_id)
        spec = templates.get(notice.kind)
        if (
            not spec
            or not sub
            or sub.credits <= 0
            or sub.template_id != spec["template_id"]
            or not user.settings.get(notice.kind, DEFAULT_SETTINGS[notice.kind])
        ):
            db.session.rollback()
            continue
        r = retirement(user.profile) or {}
        context = {
            "message": notice.text[:20],
            "nickname": user.profile.get("nickname", "用户")[:20],
            "date": datetime.now(SHANGHAI).strftime("%Y-%m-%d"),
            "years": str(r.get("years", 0)),
            "retirement_year": str(r.get("year", "")),
        }
        try:
            data = {
                k: {"value": str(v).format(**context)} for k, v in spec["data"].items()
            }
            result = requests.post(
                "https://api.weixin.qq.com/cgi-bin/message/subscribe/send",
                params={"access_token": wechat.access_token()},
                json={
                    "touser": user.openid,
                    "template_id": spec["template_id"],
                    "page": spec.get("page", "pages/home/index"),
                    "data": data,
                    "miniprogram_state": "formal",
                    "lang": "zh_CN",
                },
                timeout=10,
            ).json()
            if result.get("errcode") == 0:
                notice.delivered = True
                sub.credits -= 1
                sent += 1
            else:
                # Never silently report delivery. Reauthorization can clear a refusal.
                notice.delivery_error = str(result.get("errcode", "invalid-response"))[
                    :128
                ]
                if result.get("errcode") == 43101:
                    sub.credits = 0
                failed += 1
            db.session.commit()
        except (requests.RequestException, wechat.WechatError):
            db.session.rollback()
            failed += 1
        except (KeyError, ValueError):
            notice.delivery_error = "invalid-template-fields"
            db.session.commit()
            failed += 1
    return {"sent": sent, "failed": failed}


@api.post("/jobs/run")
def scheduled_job():
    expected = current_app.config.get("JOB_SECRET", "")
    supplied = request.headers.get("X-Job-Secret", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise ApiError("无权运行任务", 403)
    hot_ids(force=True)
    schedule_reminders()
    return ok(dispatch_notifications())

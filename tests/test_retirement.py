import base64
import io
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from PIL import Image
from wxcloudrun import create_app, db
from wxcloudrun.retirement_models import User, Post, Wish, Milestone
from wxcloudrun.retirement import retirement, SHANGHAI, today_start
from wxcloudrun.wechat import WechatError


@pytest.fixture
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "test-only-secret",
            "WECHAT_APPSECRET": "test-secret",
        }
    )
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    with patch(
        "wxcloudrun.wechat.login", side_effect=lambda code: "openid-" + code
    ), patch("wxcloudrun.wechat.check_text"), patch("wxcloudrun.wechat.check_image"):
        yield app.test_client()


def auth(client, name="alice"):
    r = client.post("/api/user/login", json={"code": name})
    assert r.status_code == 200, r.json
    return {"Authorization": "Bearer " + r.json["data"]["token"]}


def profile(client, h, **changes):
    payload = {
        "nickname": "规划用户",
        "birth_year": 1980,
        "birth_month": 6,
        "expected_retire_age": 60,
        "is_retired": False,
        "city": "大理",
        "bio": "",
        "avatar_url": "",
    }
    payload.update(changes)
    return client.put("/api/user/profile", headers=h, json=payload)


def publish(client, h, **changes):
    payload = {
        "content": "想在大理租一个小院，种花养猫过慢生活",
        "dimensions": ["location"],
        "images": [],
        "custom_tags": ["大理"],
        "expense_note": "",
    }
    payload.update(changes)
    r = client.post("/api/posts", json=payload, headers=h)
    assert r.status_code == 200, r.json
    return r.json["data"]["id"]


def test_guest_and_spoofed_identity(client):
    assert client.get("/api/posts").status_code == 200
    assert client.get("/api/wishes").status_code == 200
    assert (
        client.post(
            "/api/blueprint/item",
            headers={"X-WX-OPENID": "someone"},
            json={"dimension": "location", "content": "私有想法"},
        ).status_code
        == 401
    )
    h = auth(client)
    assert "openid" not in client.get("/api/user/profile", headers=h).json["data"]
    assert "token" not in client.get("/api/home", headers=h).json["data"]


def test_profile_validation_and_countdown(client):
    h = auth(client)
    assert profile(client, h).status_code == 200
    assert profile(client, h, expected_retire_age=45).status_code == 400
    assert profile(client, h, birth_year=True).status_code == 400
    assert profile(client, h, is_retired="false").status_code == 400
    assert profile(client, h, nickname="坏<script>").status_code == 400
    p = {
        "birth_year": 1980,
        "expected_retire_age": 60,
        "birth_month": 1,
        "is_retired": False,
    }
    # Formula in PRD yields 2040, not 2044; 2026-06 -> 13y7m to 2040-01.
    r = retirement(p, datetime(2026, 6, 1, tzinfo=SHANGHAI))
    assert (r["year"], r["years"], r["months"]) == (2040, 13, 7)
    p.update(birth_year=1960, is_retired=True, birth_month=6)
    r = retirement(p, datetime(2026, 9, 1, tzinfo=SHANGHAI))
    assert (r["years"], r["months"]) == (6, 3)


def test_blueprint_privacy_edit_delete_and_limits(client):
    a, b = auth(client), auth(client, "bob")
    value = {"dimension": "location", "content": "想要一个有院子的家", "tags": ["院子"]}
    r = client.post("/api/blueprint/item", json=value, headers=a)
    item = r.json["data"]["id"]
    assert client.get("/api/blueprint/list", headers=b).json["data"]["items"] == []
    assert (
        client.put("/api/blueprint/item/" + item, json=value, headers=b).status_code
        == 404
    )
    assert client.delete("/api/blueprint/item/" + item, headers=b).status_code == 404
    assert (
        client.post(
            "/api/blueprint/item", json={**value, "content": "字" * 201}, headers=a
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/blueprint/item", json={**value, "tags": ["a"] * 6}, headers=a
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/blueprint/item", json={**value, "dimension": "fake"}, headers=a
        ).status_code
        == 400
    )
    assert client.get("/api/home", headers=a).json["data"]["complete"] == 1
    assert client.delete("/api/blueprint/item/" + item, headers=a).status_code == 200
    assert client.get("/api/home", headers=a).json["data"]["complete"] == 0


def test_collection_idempotent_source_preserved(client):
    a, b = auth(client), auth(client, "bob")
    profile(client, a)
    pid = publish(client, a, content="生活" * 220)
    x = client.post(
        "/api/posts/" + pid + "/collect", json={"dimension": "location"}, headers=b
    ).json["data"]
    y = client.post(
        "/api/posts/" + pid + "/collect", json={"dimension": "daily"}, headers=b
    ).json["data"]
    assert (
        x["id"] == y["id"] and len(x["content"]) == 200 and y["dimension"] == "location"
    )
    assert client.delete("/api/posts/" + pid, headers=b).status_code == 404
    assert client.delete("/api/posts/" + pid, headers=a).status_code == 200
    rows = client.get("/api/blueprint/list", headers=b).json["data"]["items"]
    assert len(rows) == 1 and rows[0]["source_deleted"]
    assert client.get("/api/posts/" + pid).status_code == 404


def test_reaction_retry_and_cancel(client):
    a, b = auth(client), auth(client, "bob")
    profile(client, a)
    pid = publish(client, a)
    url = "/api/posts/" + pid + "/like"
    for _ in range(2):
        r = client.post(url, json={"liked": True}, headers=b)
        assert r.json["data"]["like_count"] == 1
    assert (
        client.post(url, json={"liked": False}, headers=b).json["data"]["like_count"]
        == 0
    )
    assert client.post(url, json={"liked": 1}, headers=b).status_code == 400


def test_wish_daily_quota_cannot_reset_by_deleting(client, app):
    h = auth(client)
    profile(client, h)
    ids = []
    for _ in range(3):
        r = client.post(
            "/api/wishes",
            headers=h,
            json={"content": "退休后我想去海边慢慢散步", "dimension": "daily"},
        )
        assert r.status_code == 200, r.json
        ids.append(r.json["data"]["id"])
    client.delete("/api/wishes/" + ids[0], headers=h)
    assert client.get("/api/wishes/quota", headers=h).json["data"]["remaining"] == 0
    assert (
        client.post(
            "/api/wishes", headers=h, json={"content": "退休后我想去海边慢慢散步"}
        ).status_code
        == 429
    )
    with app.app_context():
        Wish.query.update({"created_at": today_start() - timedelta(seconds=1)})
        db.session.commit()
    assert client.get("/api/wishes/quota", headers=h).json["data"]["remaining"] == 3


def test_comments_depth_and_report_unique_users(client):
    a = auth(client)
    profile(client, a)
    pid = publish(client, a)
    url = "/api/posts/" + pid + "/comments"
    c = client.post(url, headers=a, json={"content": "喜欢这样的生活"}).json["data"][
        "id"
    ]
    reply = client.post(
        url, headers=a, json={"content": "我也一样", "parent_id": c}
    ).json["data"]["id"]
    assert (
        client.post(
            url, headers=a, json={"content": "再回复", "parent_id": reply}
        ).status_code
        == 400
    )
    for i in range(5):
        h = auth(client, "reporter" + str(i))
        for _ in range(2):
            response = client.post(
                "/api/posts/" + pid + "/report", headers=h, json={"reason": "其他"}
            )
            if response.status_code != 200:
                assert i == 4
        if i < 4:
            assert client.get("/api/posts/" + pid).status_code == 200
    assert client.get("/api/posts/" + pid).status_code == 404
    assert (
        client.get("/api/posts?mine=1&status=rejected", headers=a).json["data"][
            "items"
        ][0]["id"]
        == pid
    )


def test_moderation_fail_closed(client):
    h = auth(client)
    profile(client, h)
    with patch(
        "wxcloudrun.wechat.check_text", side_effect=WechatError("内容审核未通过")
    ):
        assert (
            client.post(
                "/api/posts",
                headers=h,
                json={"content": "这是一段不该发布的生活内容", "dimensions": ["daily"]},
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/api/wishes", headers=h, json={"content": "这是一段不该发布的愿望内容"}
            ).status_code
            == 503
        )
    assert client.get("/api/posts").json["data"]["items"] == []
    assert client.get("/api/wishes").json["data"]["items"] == []


def test_media_validation_ownership_and_moderation(client):
    a, b = auth(client), auth(client, "bob")
    assert (
        client.post("/api/media", headers=a, json={"base64": "bad!"}).status_code == 400
    )
    out = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(out, "PNG")
    encoded = base64.b64encode(out.getvalue()).decode()
    with patch(
        "wxcloudrun.wechat.check_image", side_effect=WechatError("图片审核失败")
    ):
        assert (
            client.post("/api/media", headers=a, json={"base64": encoded}).status_code
            == 503
        )
    r = client.post("/api/media", headers=a, json={"base64": encoded})
    url = r.json["data"]["url"]
    assert client.get(url).mimetype == "image/jpeg"
    profile(client, b)
    assert (
        client.post(
            "/api/posts",
            headers=b,
            json={
                "content": "这里是自己的生活分享正文",
                "dimensions": ["daily"],
                "images": [url],
            },
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/posts",
            headers=b,
            json={
                "content": "这里是自己的生活分享正文",
                "dimensions": ["daily"],
                "images": ["http://127.0.0.1/secret"],
            },
        ).status_code
        == 400
    )


def test_blueprint_pagination(client):
    h = auth(client)
    for i in range(52):
        client.post(
            "/api/blueprint/item",
            headers=h,
            json={"dimension": "health", "content": "第{}条想法".format(i)},
        )
    r = client.get("/api/blueprint/list", headers=h).json["data"]
    assert len(r["items"]) == 50 and r["has_more"]
    r2 = client.get("/api/blueprint/list?page=2", headers=h).json["data"]
    assert len(r2["items"]) == 2 and not r2["has_more"]
    assert not set(x["id"] for x in r["items"]) & set(x["id"] for x in r2["items"])


def test_milestone_only_after_ack_and_settings(client):
    h = auth(client)
    birth = datetime.now(SHANGHAI).year - 58
    assert (
        profile(client, h, birth_year=birth, expected_retire_age=60).status_code == 200
    )
    home = client.get("/api/home", headers=h).json["data"]
    assert home["milestone"]["kind"] == "3"
    home2 = client.get("/api/home", headers=h).json["data"]
    assert home2["milestone"]["kind"] == "3"
    assert client.post("/api/milestones/3/ack", headers=h, json={}).status_code == 200
    assert client.get("/api/home", headers=h).json["data"]["milestone"] is None
    assert (
        client.put("/api/user/settings", headers=h, json={"wish": True}).status_code
        == 200
    )
    assert (
        client.put(
            "/api/user/settings", headers=h, json={"last_remaining_months": 0}
        ).status_code
        == 400
    )


def test_wechat_response_never_publishes_review_or_error(app):
    from wxcloudrun.wechat import check_text

    with app.app_context(), patch(
        "wxcloudrun.wechat.access_token", return_value="test"
    ):
        for response in [
            {"errcode": 0, "result": {"suggest": "review"}},
            {"errcode": 40001},
            {"errcode": 0},
        ]:
            with patch("wxcloudrun.wechat.requests.post") as post:
                post.return_value.json.return_value = response
                with pytest.raises(WechatError):
                    check_text("测试", "openid")


def test_feed_filter_does_not_match_text(client):
    h = auth(client)
    profile(client, h)
    a = publish(
        client,
        h,
        content="location 这个词出现在正文但不应匹配维度筛选",
        dimensions=["daily"],
    )
    b = publish(client, h, dimensions=["location", "daily"])
    r = client.get("/api/posts?dimension=location").json["data"]["items"]
    assert [p["id"] for p in r] == [b]
    assert (
        client.put(
            "/api/posts/" + b,
            headers=h,
            json={
                "content": "现在我想换成健康管理的生活分享",
                "dimensions": ["health"],
            },
        ).status_code
        == 200
    )
    assert client.get("/api/posts?dimension=location").json["data"]["items"] == []


def test_hot_ranking_hourly_snapshot_and_removed_content(client, app):
    from wxcloudrun.retirement_models import HotSnapshot

    a, b = auth(client), auth(client, "bob")
    profile(client, a)
    ids = []
    for i in range(2):
        ids.append(
            client.post(
                "/api/wishes",
                headers=a,
                json={"content": "退休愿望{}，慢慢享受有趣生活".format(i)},
            ).json["data"]["id"]
        )
    client.post("/api/wishes/" + ids[0] + "/like", headers=b, json={"liked": True})
    r = client.get("/api/wishes?sort=hot").json["data"]["items"]
    assert r[0]["id"] == ids[0]
    client.post("/api/wishes/" + ids[0] + "/like", headers=b, json={"liked": False})
    client.post("/api/wishes/" + ids[1] + "/like", headers=b, json={"liked": True})
    assert client.get("/api/wishes?sort=hot").json["data"]["items"][0]["id"] == ids[0]
    with app.app_context():
        snapshot = db.session.get(HotSnapshot, "global")
        snapshot.updated_at -= timedelta(hours=2)
        db.session.commit()
    assert client.get("/api/wishes?sort=hot").json["data"]["items"][0]["id"] == ids[1]
    client.delete("/api/wishes/" + ids[1], headers=a)
    assert len(client.get("/api/wishes?sort=hot").json["data"]["items"]) == 1


def test_subscription_delivery_requires_config_consent_and_job_secret(client, app):
    import json
    from wxcloudrun.retirement_models import Notification, Subscription
    from wxcloudrun.retirement import dispatch_notifications

    h = auth(client)
    profile(client, h)
    assert client.post("/api/jobs/run", json={}).status_code == 403
    assert (
        client.post(
            "/api/user/subscriptions",
            headers=h,
            json={"kind": "comment", "template_id": "fake"},
        ).status_code
        == 400
    )
    app.config["SUBSCRIPTION_TEMPLATES_JSON"] = json.dumps(
        {"comment": {"template_id": "test-template", "data": {"thing1": "{message}"}}}
    )
    assert (
        client.get("/api/config").json["data"]["subscription_templates"]["comment"]
        == "test-template"
    )
    assert (
        client.post(
            "/api/user/subscriptions",
            headers=h,
            json={"kind": "comment", "template_id": "test-template"},
        ).status_code
        == 200
    )
    with app.app_context():
        user = User.query.one()
        db.session.add(
            Notification(user_id=user.id, kind="comment", text="新的评论提醒")
        )
        db.session.commit()
        with patch("wxcloudrun.retirement.requests.post") as post, patch(
            "wxcloudrun.wechat.access_token", return_value="test"
        ):
            post.return_value.json.return_value = {"errcode": 0}
            assert dispatch_notifications() == {"sent": 1, "failed": 0}
            assert dispatch_notifications()["sent"] == 0
            assert db.session.get(Subscription, (user.id, "comment")).credits == 0
            payload = post.call_args.kwargs["json"]
            assert (
                payload["touser"].startswith("openid-")
                and payload["data"]["thing1"]["value"] == "新的评论提醒"
            )


def test_invalid_json_and_dimensions(client):
    h = auth(client)
    profile(client, h)
    assert (
        client.post(
            "/api/blueprint/item",
            headers=h,
            data="not-json",
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/posts",
            headers=h,
            json={"content": "这里是用于校验的内容正文", "dimensions": [["daily"]]},
        ).status_code
        == 400
    )
    assert client.get("/api/posts?page=oops").status_code == 400
    assert profile(client, h, avatar_url=123).status_code == 400

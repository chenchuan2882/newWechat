import uuid
from datetime import datetime
from wxcloudrun import db


def uid():
    return uuid.uuid4().hex


class User(db.Model):
    __tablename__ = "retirement_users"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    openid = db.Column(db.String(128), unique=True, nullable=False)
    profile = db.Column(db.JSON, nullable=False, default=dict)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Post(db.Model):
    __tablename__ = "retirement_posts"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    user_id = db.Column(
        db.String(32), db.ForeignKey(User.id), nullable=False, index=True
    )
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(16), default="published", nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Wish(db.Model):
    __tablename__ = "retirement_wishes"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    user_id = db.Column(
        db.String(32), db.ForeignKey(User.id), nullable=False, index=True
    )
    content = db.Column(db.String(80), nullable=False)
    dimension = db.Column(db.String(16))
    status = db.Column(db.String(16), default="published", nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class BlueprintItem(db.Model):
    __tablename__ = "retirement_blueprint_items"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    user_id = db.Column(
        db.String(32), db.ForeignKey(User.id), nullable=False, index=True
    )
    dimension = db.Column(db.String(16), nullable=False)
    content = db.Column(db.String(200), nullable=False)
    tags = db.Column(db.JSON, nullable=False, default=list)
    source_type = db.Column(db.String(16), default="self", nullable=False)
    source_post_id = db.Column(db.String(32), db.ForeignKey(Post.id), nullable=True)
    source_author = db.Column(db.String(16))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "source_post_id"),)


class Comment(db.Model):
    __tablename__ = "retirement_comments"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    post_id = db.Column(
        db.String(32), db.ForeignKey(Post.id), nullable=False, index=True
    )
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), nullable=False)
    parent_id = db.Column(db.String(32), db.ForeignKey("retirement_comments.id"))
    content = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Reaction(db.Model):
    __tablename__ = "retirement_reactions"
    __table_args__ = (db.Index("ix_reactions_target", "kind", "target_id"),)
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), primary_key=True)
    kind = db.Column(db.String(16), primary_key=True)
    target_id = db.Column(db.String(32), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Report(db.Model):
    __tablename__ = "retirement_reports"
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), primary_key=True)
    post_id = db.Column(db.String(32), db.ForeignKey(Post.id), primary_key=True)
    reason = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Milestone(db.Model):
    __tablename__ = "retirement_milestones"
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), primary_key=True)
    kind = db.Column(db.String(32), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Media(db.Model):
    __tablename__ = "retirement_media"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), nullable=False)
    content = db.Column(db.LargeBinary(length=8388608), nullable=False)
    mime = db.Column(db.String(32), nullable=False, default="image/jpeg")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
    __tablename__ = "retirement_notifications"
    id = db.Column(db.String(32), primary_key=True, default=uid)
    user_id = db.Column(
        db.String(32), db.ForeignKey(User.id), nullable=False, index=True
    )
    text = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="comment")
    delivered = db.Column(db.Boolean, nullable=False, default=False)
    delivery_error = db.Column(db.String(128))
    read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class PostDimension(db.Model):
    __tablename__ = "retirement_post_dimensions"
    post_id = db.Column(db.String(32), db.ForeignKey(Post.id), primary_key=True)
    dimension = db.Column(db.String(16), primary_key=True, index=True)


class HotSnapshot(db.Model):
    __tablename__ = "retirement_hot_snapshots"
    id = db.Column(db.String(16), primary_key=True)
    ids = db.Column(db.JSON, nullable=False, default=list)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Subscription(db.Model):
    __tablename__ = "retirement_subscriptions"
    user_id = db.Column(db.String(32), db.ForeignKey(User.id), primary_key=True)
    kind = db.Column(db.String(16), primary_key=True)
    template_id = db.Column(db.String(128), nullable=False)
    credits = db.Column(db.Integer, nullable=False, default=0)


# Store Chinese text and emoji correctly even when the original DB default is utf8.
for table in db.metadata.tables.values():
    if table.name.startswith("retirement_"):
        table.dialect_options["mysql"]["charset"] = "utf8mb4"

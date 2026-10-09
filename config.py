import os
from urllib.parse import quote_plus

DEBUG = False
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
    "mysql+pymysql://{}:{}@{}/{}?charset=utf8mb4".format(
        quote_plus(os.getenv("MYSQL_USERNAME", "root")),
        quote_plus(os.getenv("MYSQL_PASSWORD", "")),
        os.getenv("MYSQL_ADDRESS", "127.0.0.1:3306"),
        os.getenv("MYSQL_DATABASE", "flask_demo"),
    )
)
SECRET_KEY = os.getenv("SESSION_SECRET", "")
WECHAT_APPID = os.getenv("WECHAT_APPID", "wx6e5527ee2c4beffa")
WECHAT_APPSECRET = os.getenv("WECHAT_APPSECRET", "")
MAX_CONTENT_LENGTH = 2 * 1024 * 1024
SESSION_MAX_AGE = 7 * 24 * 3600
# JSON mapping kind -> {template_id, data:{template_field:"{message}"}, page}.
SUBSCRIPTION_TEMPLATES_JSON = os.getenv("WECHAT_SUBSCRIPTION_TEMPLATES", "{}")
JOB_SECRET = os.getenv("JOB_SECRET", "")

# 凡事预则立 · 退休生活规划小程序

基于用户提供的 [PRD v1](docs/PRD-v1.txt) 实现；本版本不包含 AI。后端业务接口位于 `/api`，原生小程序位于 `miniprogram/`。

## 已实现

- 首页：按时段问候、按月退休倒计时、已退休展示、蓝图完整度、最近48小时生活分享推荐。
- 用户：微信登录、三步引导、资料编辑、可选出生月份、头像上传、游客只读浏览、退出登录清除私有缓存。
- 蓝图：五维私有记录、编辑删除、标签、每页50条、收藏去重、来源删除后保留快照、离线缓存。
- 发现：时间倒序、维度筛选、每页20条、图片分享、文字/图片审核、编辑删除、作者主页、点赞、评论/一级回复、评论点赞、微信分享。
- 愿望：热门/最新/维度筛选、每天3条北京时间额度、删除不恢复额度、幂等+1、最近5位互动用户、加入蓝图。
- 社区：不同用户累计5次举报自动下线、作者消息提醒、我的发布/收藏/愿望、应用内消息、通知开关。
- 提醒：持久化里程碑确认、生日月年度回顾、小时热门缓存、可配置微信订阅消息发送及受保护的定时任务入口。

## 项目结构

```text
miniprogram/             微信原生 WXML / WXSS / JS，15个页面
wxcloudrun/retirement.py 业务接口与输入校验
wxcloudrun/retirement_models.py MySQL 数据模型
wxcloudrun/wechat.py     微信登录与内容安全接口
scripts/                小程序静态检查
 tests/                 API 集成测试（SQLite、模拟微信接口）
 docs/                  原始PRD、部署与验收说明
```

## 本地后端

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
# .env 不会自动加载，请通过安全的运行环境注入变量。
export DATABASE_URL='sqlite:///development.db'
export SESSION_SECRET='<自行生成随机值>'
export WECHAT_APPSECRET='<从微信后台获取>'
.venv/bin/python -m flask --app wxcloudrun init-db
.venv/bin/python -m flask --app wxcloudrun run --port 8080
```

SQLite 用于本地开发与测试；生产使用现有 MySQL。真实微信登录和内容审核仍需有效 AppSecret，项目没有开发后门、默认演示账号或绕过审核开关。

## 微信开发者工具

导入**仓库根目录**，读取 `project.config.json`，AppID 已设为 `wx6e5527ee2c4beffa`，代码目录是 `miniprogram/`。

前端使用 `wx.cloud.callContainer`，环境 `prod-d5gjoz9hoc91797d2`、服务 `flask-0zs5`。这不是网页，云托管推送仅更新后端；小程序前端仍需在开发者工具上传、体验版真机验证和微信审核发布。

## 部署

详见 [部署说明](docs/DEPLOYMENT.md)。容器启动会创建缺失表，不会删除已有表或数据。不要把密码、AppSecret、会话密钥或 `.env` 提交到 Git。

## 检查

```bash
.venv/bin/python -m pytest -q
node scripts/check-miniprogram.js
python3 scripts/check-wxml.py
```

测试使用模拟微信响应和 SQLite，不能证明微信审核接口、真实 MySQL、前端真机表现或云托管流水线已运行成功。性能阈值需在真实环境测量。

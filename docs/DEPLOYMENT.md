# 微信云托管部署与验收

## 已知配置

| 项目 | 值 |
| --- | --- |
| 小程序 AppID | wx6e5527ee2c4beffa |
| 云托管环境 | prod-d5gjoz9hoc91797d2 |
| 服务 | flask-0zs5 |
| Git 分支 | master |
| 服务域名 | https://flask-0zs5-325475-12-1301984929.sh.run.tcloudbase.com |

登录邮箱、数据库密码不进入代码仓库。

## 生产环境变量

| 变量 | 说明 |
| --- | --- |
| MYSQL_ADDRESS | 现有 MySQL 地址:端口，尚未由用户提供；如控制台已有配置则沿用 |
| MYSQL_USERNAME | 数据库用户名，通过控制台配置 |
| MYSQL_PASSWORD | 数据库密码，通过控制台配置 |
| MYSQL_DATABASE | 沿用现有数据库（默认名称 flask_demo），必须为已存在数据库 |
| SESSION_SECRET | 至少32字节随机值，所有实例保持一致；修改后已有登录失效 |
| WECHAT_APPID | 默认 wx6e5527ee2c4beffa |
| WECHAT_APPSECRET | 小程序后台的 AppSecret，微信登录和内容安全接口必需 |
| JOB_SECRET | 调度任务的独立随机密钥 |
| WECHAT_SUBSCRIPTION_TEMPLATES | 订阅消息模板配置 JSON，未配置时只显示应用内消息 |

也可用 `DATABASE_URL` 设置完整数据库 URI，优先于 MYSQL 变量。生产日志不主动输出密码或微信会话密钥。

容器端口保持80。启动执行 `flask init-db` 仅创建缺失的 `retirement_` 业务表，不删除已有数据。新表使用 utf8mb4 支持中文与 emoji。需要创建表权限；建表失败会停止启动。对已存在新表的后续字段修改应使用迁移，而非依赖 create_all。

## 鉴权与审核

客户端 `wx.login` 获取临时 code，服务端通过官方 `jscode2session` 验证后签发7天会话。忽略客户端可伪造的 X-WX-OPENID，不通过公网传入的身份 header 授权私有记录。

需在微信后台核实服务端调用凭证/IP设置及内容安全权限。文字采用 `msg_sec_check` v2（包括用户 openid 与 scene），图片经服务端解码、重编码后调用 `img_sec_check`。若账号不支持该图片接口，发布会失败，必须在真实接入验收时确认可用性或切换到官方异步媒体审核流程；不能关闭审核直接上线。审核超时、拒绝或待复核都不会发布。

## 图片存储的技术调整

PRD 计划云存储，当前版本为复用既有 Flask + MySQL 采用数据库图片表，随机ID媒体接口提供头像和公开分享图片。上传前压缩至800KB，服务端再次验证尺寸、重编码并审核，只允许引用自己上传的图片。上线需添加服务域名到小程序 downloadFile 合法域名以显示图片。

这是明确的 PRD 架构差异：后续扩量应迁移到云存储和CDN，配置生命周期清理未使用图片。本版没有云存储环境ID，不能凭云托管环境ID假定文件存储已配置。

## 定时任务与微信订阅消息

在云端调度平台配置每小时发送一次 `POST /api/jobs/run`，通过 `X-Job-Secret` 请求头传入 JOB_SECRET，使用HTTPS。任务刷新热门前100条、检查生日与里程碑、发送已授权订阅消息。未配置外部调度时，热门列表仍在访问后最多每小时刷新，首页仍可展示里程碑与生日月回顾；微信外部消息不会自动发送。

也可在同配置环境执行：

```bash
python -m flask --app wxcloudrun refresh-hot
python -m flask --app wxcloudrun dispatch-reminders
```

`WECHAT_SUBSCRIPTION_TEMPLATES` 示例形状（必须替换为微信后台实际审批的模板ID和字段）：

```json
{
  "comment": {
    "template_id": "实际模板ID",
    "page": "pages/notifications/index",
    "data": {"thing1": "{message}", "time2": "{date}"}
  }
}
```

支持 kind：milestone、annual、collection、comment、wish；字段占位符支持 message（20字以内）、nickname、date、years、retirement_year。模板数据类型/长度必须与实际审批模板一致。开启通知设置时若有模板，会请求微信订阅授权。发送时微信再次验证真实授权，未授权不发送，失败记录不会被标记为成功。网络不确定失败可能需要运营核查，不能保证严格一次外部消息投递。

## PRD 决策与差异

- 不接入AI、不实现付费、搭子匹配、PDF导出或算法推荐。
- 名称暂用“凡事预则立”；文档混用“霁念墙/许愿墙”，前端统一“许愿墙/愿望”。
- 所有完善资料的用户均可发布，符合主PRD发布条款；评论进入本版。
- 蓝图只记录文字与标签，公开分享可附图片。
- 倒计时按出生年份＋退休年龄计算，增加可选出生月份，缺省1月并展示“估算”提示。原文1980年出生、60岁退休、2026年6月剩13年6月的示例与公式不符；正确退休年为2040，若按2040年1月则剩13年7月。
- 年度回顾展示过去365天新增想法及收藏、未填维度；不保存每次历史编辑版本，删除的想法不计入当前回顾。
- 图片排序支持左右拖动调整以及前移按钮；不实现复杂自由拖拽动画。
- 评论预览为前三条热门一级评论，展开完整分页列表；一级回复用回复标识展示。
- 内容安全为同步审核，审核中未生成公开记录；“审核中”列表通常为空，拒绝发布直接提示修改。累计举报下线的内容出现在“已下线”列表。
- 不承诺实际2秒审核、1.5秒首屏或300ms后端响应；这些阈值需真实环境验证。
- 不承诺24小时人工举报处理，当前按PRD自动下线并记录反馈。

## 上线前实际验收

1. 云托管控制台确认流水线关联该仓库 master，部署 Dockerfile 并配置上述变量。
2. 确认建表成功和 `/api/health`；旧 `/api/count` 应返回404。
3. 开发者工具导入根目录，确认环境关联、服务访问权限、图片合法域名及服务调用权限。
4. 用两个真实微信账号分别登录，检查昵称头像、资料保存、私有蓝图隔离、分享审核、收藏来源删除、评论及愿望额度。
5. 配置模板及调度，真机授权并检查订阅消息实际投递。
6. 完成隐私保护指引、主体/联系方式、服务类目、社区内容规范和微信审核要求；应用内说明不替代平台隐私配置。
7. 真机检查长文、键盘遮挡、拖动图片、小屏/大字体、离线缓存与性能，前端单独上传审核。

## 清理后重新部署

旧计数器接口、欢迎页、辅助模块、run.py 和仅用于初始模板的 container.config.json 已删除。生产入口仍为 Dockerfile → entrypoint.sh → Gunicorn，端口80。数据库名称为兼容已有环境继续沿用，清理代码不执行删表。

1. 在既有服务 flask-0zs5 的流水线中选择 newWechat/master 最新提交，重新构建并发布；构建目录为仓库根目录，Dockerfile 路径为 Dockerfile。
2. 核对 MYSQL_ADDRESS、MYSQL_USERNAME、MYSQL_PASSWORD、MYSQL_DATABASE、SESSION_SECRET 和 WECHAT_APPSECRET；查看构建与启动日志，确认 init-db 成功。
3. 发布后访问 /api/health，应返回包含 retirement-mvp-1 的 JSON；访问 /api/posts 应返回业务 JSON，/api/count 应返回404。
4. GitHub Application checks 仅验证代码，不能证明云托管发布成功。小程序前端仍需独立上传。

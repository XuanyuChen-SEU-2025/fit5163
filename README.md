# 安全的多层级博客活动分析系统

一个使用 Python `Flask` 实现的演示项目，覆盖以下能力：

- Visitors can browse anonymously or log in as visitor accounts.
- Anonymous visitors generate anonymous activity data.
- Logged-in visitors generate activity data linked to their visitor account.
- Blogger accounts are separate and are used only for dashboard analytics access.
- Basic and Premium blogger roles control analytics visibility.
- 安全活动追踪：记录页面浏览量、停留时长、点赞、评论和分享。
- 加密存储：visitor profile JSON、activity details、评论内容使用 `Fernet` 加密。
- 权限分级：Basic Blogger 查看基础 analytics；Premium Blogger 查看 time series、journey mapping 和 session snapshots。

## 演示账号

Visitor demo account:

- username: `visitor1`
- password: `visit123`

备用 Visitor demo account:

- username: `visitor2`
- password: `visit123`

Blogger demo accounts:

- Basic Blogger: `lin / blog123`
- Premium Blogger: `helen / blog123`

Visitor 登录只用于前台浏览、点赞、分享、评论和停留时间归属；Blogger 登录只用于后台 dashboard analytics access。visitor 账号不能访问 blogger dashboard。

## 在 `D:\anaconda3\envs` 创建环境

```powershell
conda create -y -p D:\anaconda3\envs\secure-blog-analytics python=3.11
conda run -p D:\anaconda3\envs\secure-blog-analytics python -m pip install -r requirements.txt
```

## 运行

```powershell
conda run -p D:\anaconda3\envs\secure-blog-analytics python app.py
```

启动后访问：

- 前台首页：`https://127.0.0.1:5000/`
- 访客登录：`https://127.0.0.1:5000/visitor/login`
- 博主后台登录：`https://127.0.0.1:5000/login`

浏览器首次访问会提示自签名证书风险，这是演示环境常见现象；继续访问即可看到 `HTTPS` 页面。

## 访客与博主权限

- 未登录访客会记录为 `anonymous visitor session`，可以继续浏览文章、点赞、分享、评论和产生停留时间。
- 已登录访客会记录为 `authenticated visitor`，行为会绑定到 visitor account。
- Basic Blogger 可以看到总访客数、访客分类分布、已登录访客活动数量和基础文章表现。
- Premium Blogger 可以看到更详细的匿名访问路径、已登录访客路径、time series 和 session snapshots。

## 安全说明

- visitor 与 blogger 密码均使用 Werkzeug password hashing 存储。
- 评论正文、activity details、visitor profile JSON 均使用 Fernet 加密后落库。
- like、share、comment、dwell 和 visitor login/logout 保持 CSRF 保护。
- `instance/`、数据库文件和 `.key` 文件由 `.gitignore` 排除，不应加入版本控制。

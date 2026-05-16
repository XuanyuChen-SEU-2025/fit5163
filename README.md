# 安全的多层级博客活动分析系统

一个使用 Python `Flask` 实现的演示项目，覆盖以下能力：

- 安全活动追踪：记录页面浏览量、停留时长、点赞、评论、分享
- 安全传输：开发模式直接通过 `HTTPS/TLS` 启动
- 加密存储：会话画像、行为明细、评论内容使用 `Fernet` 加密
- 权限分级：普通博主查看基础指标，高级博主查看完整行为路径图谱与时间序列
- 前台与后台：包含博客前台页面、文章详情页和博主管理仪表盘

## 演示账号

- 普通博主：`lin / blog123`
- 高级博主：`helen / blog123`

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
- 博主后台：`https://127.0.0.1:5000/login`

浏览器首次访问会提示自签名证书风险，这是演示环境常见现象；继续访问即可看到 `HTTPS` 页面。

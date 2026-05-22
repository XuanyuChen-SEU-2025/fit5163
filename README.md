# Secure Multi-Level Blog Activity Analytics System

A demo project built with Python `Flask` that covers the following capabilities:

- Visitors can browse anonymously or log in as visitor accounts.
- Anonymous visitors generate anonymous activity data.
- Logged-in visitors generate activity data linked to their visitor account.
- Blogger accounts are separate and are used only for dashboard analytics access.
- Basic and Premium blogger roles control analytics visibility.
- Secure activity tracking records page views, dwell time, likes, comments, and shares.
- Encrypted storage protects visitor profile JSON, activity details, and comment content with `Fernet`.
- Tiered permissions let Basic Bloggers view basic analytics, while Premium Bloggers can view time series, journey mapping, and session snapshots.

## Demo Accounts

Visitor demo account:

- username: `visitor1`
- password: `visit123`

Backup Visitor demo account:

- username: `visitor2`
- password: `visit123`

Blogger demo accounts:

- Basic Blogger: `lin / blog123`
- Premium Blogger: `helen / blog123`

Visitor login is used only for public browsing, likes, shares, comments, and dwell-time attribution. Blogger login is used only for dashboard analytics access. Visitor accounts cannot access the blogger dashboard.

## Create the Environment in `D:\anaconda3\envs`

```powershell
conda create -y -p D:\anaconda3\envs\secure-blog-analytics python=3.11
conda run -p D:\anaconda3\envs\secure-blog-analytics python -m pip install -r requirements.txt
```

## Run

```powershell
conda run -p D:\anaconda3\envs\secure-blog-analytics python app.py
```

After startup, visit:

- Public homepage: `https://127.0.0.1:5000/`
- Visitor login: `https://127.0.0.1:5000/visitor/login`
- Blogger dashboard login: `https://127.0.0.1:5000/login`

On first visit, the browser may warn about a self-signed certificate. This is normal for the demo environment; continue to the site to view the `HTTPS` page.

## Visitor and Blogger Permissions

- Visitors who are not logged in are recorded as an `anonymous visitor session` and can continue browsing articles, liking, sharing, commenting, and generating dwell time.
- Logged-in visitors are recorded as an `authenticated visitor`, and their behavior is linked to a visitor account.
- Basic Bloggers can see total visitor count, visitor type distribution, logged-in visitor activity count, and basic post performance.
- Premium Bloggers can see more detailed anonymous visitor journeys, logged-in visitor journeys, time series, and session snapshots.

## Security Notes

- Visitor and blogger passwords are stored with Werkzeug password hashing.
- Comment body text, activity details, and visitor profile JSON are encrypted with Fernet before being stored in the database.
- Like, share, comment, dwell, and visitor login/logout flows remain protected by CSRF checks.
- `instance/`, database files, and `.key` files are excluded by `.gitignore` and should not be committed to version control.

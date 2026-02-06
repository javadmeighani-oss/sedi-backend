# راهنمای Setup Git و Push به GitHub

## وضعیت فعلی

✅ Git repository initialize شده
✅ فایل‌ها commit شده‌اند
✅ GitHub Actions workflow برای build فرانت ایجاد شده

## مراحل بعدی

### 1. اضافه کردن Remote Repository

اگر repository در GitHub ندارید:
```bash
# ایجاد repository جدید در GitHub (از طریق وب)
# سپس:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

اگر repository دارید:
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### 2. Push به GitHub

```bash
# Push کردن به branch main
git branch -M main
git push -u origin main
```

یا اگر branch دیگری دارید:
```bash
git push -u origin master
# یا
git push -u origin develop
```

### 3. فعال‌سازی GitHub Actions

بعد از push:
1. به GitHub repository بروید
2. به Settings > Actions > General بروید
3. مطمئن شوید که "Allow all actions and reusable workflows" فعال است
4. به Actions tab بروید
5. workflow باید به صورت خودکار اجرا شود

### 4. دانلود APK از GitHub Actions

بعد از build موفق:
1. به Actions tab در GitHub بروید
2. روی workflow run کلیک کنید
3. به بخش "Artifacts" بروید
4. APK را دانلود کنید

## ساختار Repository

```
Demo/
├── .github/
│   └── workflows/
│       └── build-frontend.yml    # GitHub Actions workflow
├── backend/                      # Backend code
├── frontend/                     # Flutter frontend
├── .gitignore                    # Git ignore rules
└── README.md
```

## نکات مهم

1. **Backend**: فعلاً فقط commit شده، برای deploy باید جداگانه انجام شود
2. **Frontend**: GitHub Actions به صورت خودکار build می‌کند
3. **Secrets**: اگر نیاز به API keys دارید، در GitHub Secrets اضافه کنید

## دستورات مفید

```bash
# بررسی remote
git remote -v

# تغییر remote URL
git remote set-url origin NEW_URL

# بررسی وضعیت
git status

# مشاهده commit‌ها
git log --oneline
```


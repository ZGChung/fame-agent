# Cookie 存放目录

小红书发布器需要 Playwright Cookie 来模拟登录。

## 使用方法

1. 运行登录脚本获取 Cookie：
```bash
pipeline auth xiaohongshu
```

这会打开浏览器窗口，你手动登录小红书创作者后台，
登录成功后 Cookie 会自动保存到 `xiaohongshu.json`。

2. 确认 Cookie 文件存在：
```bash
ls -la cookies/xiaohongshu.json
```

3. 测试发布：
```bash
pipeline publish <content_id> --platform xiaohongshu
```

## 注意事项

- Cookie 文件包含登录凭据，**不要提交到 Git**
- Cookie 有过期时间，过期后需要重新登录
- 该目录下的 `*.json` 文件已被 .gitignore 排除

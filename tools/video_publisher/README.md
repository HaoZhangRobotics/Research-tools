# 科研视频发布

本地界面可选择视频文件、撰写标题和简介、添加标签、勾选平台并生成稿件 JSON。抖音和 YouTube 提供官方 API 直发适配器；B 站、小红书和 X 可生成统一稿件并打开官方入口。每次 API 发布都需要在界面预览后明确勾选确认。

## 启动

在仓库根目录运行：

```bash
python -m pip install -r tools/video_publisher/requirements.txt
streamlit run tools/app.py
```

如需 YouTube 直发，再安装可选依赖：

```bash
python -m pip install -r tools/video_publisher/requirements-youtube.txt
```

## YouTube 设置

1. 在 Google Cloud 项目中启用 YouTube Data API v3，创建 OAuth 桌面应用凭据。
2. 将下载的凭据文件放在 `tools/video_publisher/client_secret.json`（已加入忽略规则，不会提交到 Git）。
3. 首次点击“发布到 YouTube”时，会打开 Google OAuth 授权；授权 token 保存在本地 `youtube_token.json`，同样已忽略。
4. 发布默认设为 `private`。未审核的 API 项目上传可能被限制为私享视频；公开发布资格受 Google 项目审核影响。

官方接口要求 `youtube.upload` OAuth scope。见 [YouTube 视频上传 API](https://developers.google.com/youtube/v3/docs/videos/insert)。

## 抖音设置

1. 在[抖音开放平台](https://open.douyin.com/)注册应用，申请视频发布能力及 `video.create` 权限，并完成用户授权。
2. 在仓库根目录创建 `.streamlit/secrets.toml`（该文件不要提交），填入授权得到的 access token 和对应账号 open_id：

   ```toml
   douyin_access_token = "你的用户授权 access_token"
   douyin_open_id = "对应账号的 open_id"
   ```

3. 选择抖音并点击“发布到抖音”。当前直传入口限定在 128 MB 以内；平台收到后还会进行内容审核。

抖音官方文档说明上传与发布均需申请 `video.create` 权限和用户授权；代用户发布时，界面需让用户清楚感知每次操作。见[上传视频](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/create/upload)和[创建视频](https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/create/create-video)。

## 其他平台

- **哔哩哔哩**：开放平台文档说明开发者认证通过后可申请稿件分发能力；本工具尚未实现投稿适配器。使用官方[开放平台](https://open.bilibili.com/doc/main)完成发布。
- **小红书**：当前核对到的开放平台 API 参考主要列出授权等接口，未确认面向普通创作者的通用视频投稿 API，因此只生成稿件并打开[开放平台](https://open.xiaohongshu.com/)。
- **X**：视频媒体上传与发帖需要相应 X API 项目访问权限；尚未接入媒体上传，本工具打开[X 开发者文档](https://developer.x.com/en/docs)。

这些平台权限和 API 会随平台政策变化。直发按钮只会对明确配置并选中的平台发送；未接入的平台不会被伪装成已发布。

## 本地数据和依赖

稿件副本保存在 `tools/video_publisher/output/`，视频上传暂存文件会在请求结束后删除。凭据与授权 token 不应提交。基础依赖只有 Streamlit；抖音适配器复用论文工具的 `requests` 依赖，YouTube 客户端为可选依赖。

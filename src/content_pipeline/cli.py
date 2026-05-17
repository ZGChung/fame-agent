"""
Content Pipeline — 命令行入口

提供完整的 CLI 接口用于管理 Pipeline。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import Content, ContentStatus, Platform, Pipeline
from .config import BASE_DIR, PipelineConfig
from .media.image import ImageGenerator
from .media.video import VideoGenerator
from .publishers import XiaohongshuPublisher, create_default_registry

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Jayson's Content Pipeline — 多平台社交媒体自动发布",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # --- status ---
    sub.add_parser("status", help="查看当前 Pipeline 状态")

    # --- list ---
    list_p = sub.add_parser("list", help="列出内容")
    list_p.add_argument("folder", nargs="?", default="input",
                        choices=["input", "processing", "queue", "published"],
                        help="内容文件夹")

    # --- create ---
    create_p = sub.add_parser("create", help="创建新内容")
    create_p.add_argument("--title", "-t", required=True, help="标题")
    create_p.add_argument("--body", "-b", default="", help="正文（或从 stdin 读取）")
    create_p.add_argument("--platforms", "-p", default="xiaohongshu",
                          help="目标平台，逗号分隔")

    # --- publish ---
    publish_p = sub.add_parser("publish", help="发布内容")
    publish_p.add_argument("content_id", help="内容 ID")
    publish_p.add_argument("--platform", "-p", help="目标平台（默认发布到所有配置的平台）")

    # --- video ---
    video_p = sub.add_parser("video", help="视频操作")
    video_sub = video_p.add_subparsers(dest="video_command")

    gen_p = video_sub.add_parser("generate", help="从图片生成视频")
    gen_p.add_argument("images", nargs="+", help="图片路径")
    gen_p.add_argument("--output", "-o", default="", help="输出路径")
    gen_p.add_argument("--duration", "-d", type=float, default=3.0, help="每张图片时长")

    tts_p = video_sub.add_parser("tts", help="为视频添加 TTS 配音")
    tts_p.add_argument("video", help="视频路径")
    tts_p.add_argument("text", help="配音文字")
    tts_p.add_argument("--output", "-o", default="", help="输出路径")

    music_p = video_sub.add_parser("add-music", help="添加背景音乐")
    music_p.add_argument("video", help="视频路径")
    music_p.add_argument("music", help="音乐文件路径")
    music_p.add_argument("--output", "-o", default="", help="输出路径")

    # --- image ---
    image_p = sub.add_parser("image", help="图片操作")
    image_p.add_argument("title", help="标题")
    image_p.add_argument("--body", default="", help="正文（用于生成 prompt）")
    image_p.add_argument("--output", "-o", default="", help="输出路径")

    # --- auth ---
    auth_p = sub.add_parser("auth", help="平台认证登录")
    auth_p.add_argument("platform", choices=["xiaohongshu"], help="平台")

    # --- run ---
    sub.add_parser("run", help="运行一次自动化处理")

    args = parser.parse_args()
    setup_logging(args.verbose if hasattr(args, "verbose") else False)

    if not args.command:
        parser.print_help()
        return

    try:
        _dispatch(args)
    except Exception as e:
        logger.exception("Command failed: %s", args.command)
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def _dispatch(args):
    """分发到对应的命令处理器"""

    if args.command == "status":
        _cmd_status()

    elif args.command == "list":
        _cmd_list(args.folder)

    elif args.command == "create":
        _cmd_create(args.title, args.body, args.platforms)

    elif args.command == "publish":
        _cmd_publish(args.content_id, args.platform)

    elif args.command == "video":
        _cmd_video(args)

    elif args.command == "image":
        _cmd_image(args.title, args.body, args.output)

    elif args.command == "auth":
        _cmd_auth(args.platform)

    elif args.command == "run":
        _cmd_run()


# --- 命令实现 ---

def _cmd_status():
    pipeline = Pipeline()
    status = pipeline.status()
    print("\n📊 Pipeline 状态:\n")
    print(f"  input:      {status['input']} 条")
    print(f"  processing: {status['processing']} 条")
    print(f"  queue:      {status['queue']} 条")
    print(f"  published:  {status['published']} 条")
    print()
    print("📡 平台发布器:")
    for name, ready in status["platforms"].items():
        icon = "✅" if ready else "❌"
        print(f"  {icon} {name}")
    print()


def _cmd_list(folder: str):
    pipeline = Pipeline()
    contents = pipeline.store.list_content(folder)
    if not contents:
        print(f"\n📭 {folder}/ 中没有内容\n")
        return

    print(f"\n📂 {folder}/ ({len(contents)} 条):\n")
    for c in contents:
        icon = c.emoji
        print(f"  [{c.id}] {c.title}")
        print(f"        {c.summary}")
        print()
    print(f"共 {len(contents)} 条\n")


def _cmd_create(title: str, body: str, platforms_str: str):
    platforms = [p.strip() for p in platforms_str.split(",") if p.strip()]

    # 如果正文为空，尝试从 stdin 读取
    if not body and not sys.stdin.isatty():
        body = sys.stdin.read().strip()

    pipeline = Pipeline()
    content = pipeline.create_content(title, body, platforms)
    print(f"\n✅ 内容已创建: [{content.id}] {content.title}")
    print(f"   目标平台: {', '.join(p.value for p in content.platforms)}")
    print()


def _cmd_publish(content_id: str, platform: str | None):
    pipeline = Pipeline()

    # 注册当前可用的发布器
    registry = create_default_registry()
    for name, pub in registry.all().items():
        pipeline.register_publisher(name, pub)

    if platform and not registry.get(platform):
        print(f"\n❌ 发布器 {platform} 未配置可用。")
        print("   运行 pipeline status 查看配置状态。\n")
        return

    results = pipeline.publish(content_id, platform)
    print(f"\n📤 发布结果 [{content_id}]:\n")
    for p, r in results.items():
        icon = "✅" if r.get("success") else "❌"
        err = f" — {r['error']}" if r.get("error") else ""
        url = f" → {r['url']}" if r.get("url") else ""
        print(f"  {icon} {p}{url}{err}")
    print()


def _cmd_video(args):
    vg = VideoGenerator()

    if args.video_command == "generate":
        result = asyncio.run(vg.slideshow(
            images=args.images,
            output_path=args.output,
            duration_per_image=args.duration,
        ))
        print(f"\n✅ 视频已生成: {result}\n")

    elif args.video_command == "tts":
        result = asyncio.run(vg.add_tts(
            video_path=args.video,
            text=args.text,
            output_path=args.output,
        ))
        print(f"\n✅ TTS 视频已生成: {result}\n")

    elif args.video_command == "add-music":
        result = asyncio.run(vg.add_background_music(
            video_path=args.video,
            music_path=args.music,
            output_path=args.output,
        ))
        print(f"\n✅ 背景音乐已添加: {result}\n")

    else:
        print("Usage: pipeline video {generate,tts,add-music} ...")


def _cmd_image(title: str, body: str, output_path: str):
    if not output_path:
        output_path = f"/tmp/content_cover_{title[:20].replace(' ', '_')}.jpg"

    gen = ImageGenerator()
    result = gen.generate(title, body, output_path)

    if result:
        print(f"\n✅ 图片已生成: {result}\n")
    else:
        print("\n❌ 图片生成失败。请配置 OPENAI_API_KEY 或检查 ffmpeg。\n")


def _cmd_auth(platform: str):
    """交互式登录获取 Cookie"""
    if platform == "xiaohongshu":
        _auth_xiaohongshu()


def _auth_xiaohongshu():
    """小红书 Cookie 登录"""
    print("\n🔐 小红书 Cookie 登录\n")
    print("即将打开浏览器，请手动登录小红书创作者后台。")
    print("登录成功后 Cookie 会自动保存。\n")
    print("提示：需要先安装 Playwright:")
    print("  pip install playwright && playwright install chromium\n")

    async def login():
        publisher = XiaohongshuPublisher(headless=False)
        try:
            await publisher._ensure_browser()
            await publisher._page.goto(
                "https://creator.xiaohongshu.com/login"
            )
            print("请在浏览器中登录...")
            print("登录后按 Enter 继续...")
            input()

            # 保存 Cookie
            cookies = await publisher._context.cookies()
            cookie_path = publisher.cookie_path
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            cookie_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✅ Cookie 已保存到: {cookie_path}")
            print(f"   共 {len(cookies)} 条 Cookie\n")
        finally:
            await publisher._close_browser()

    asyncio.run(login())


def _cmd_run():
    pipeline = Pipeline()
    results = pipeline.run_once()
    print(f"\n🔄 Pipeline run complete")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print()


if __name__ == "__main__":
    main()

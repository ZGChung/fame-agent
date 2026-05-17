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
from datetime import datetime
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

    # --- schedule ---
    sched_p = sub.add_parser("schedule", help="发布队列调度")
    sched_sub = sched_p.add_subparsers(dest="sched_command")

    sched_list_p = sched_sub.add_parser("list", help="查看发布队列")
    sched_list_p.add_argument("--days", "-d", type=int, default=7, help="未来 N 天 (默认 7)")

    sched_add_p = sched_sub.add_parser("add", help="加入发布队列")
    sched_add_p.add_argument("content_id", help="内容 ID")
    sched_add_p.add_argument("--at", default=None, help="计划发布时间 (YYYY-MM-DD HH:MM)")
    sched_add_p.add_argument("--priority", "-p", type=int, default=0, help="优先级 (0=普通, 越大越优先)")
    sched_add_p.add_argument("--platform", default=None, help="指定平台 (默认使用内容配置的所有平台)")

    sched_run_p = sched_sub.add_parser("run", help="处理到期队列项")
    sched_run_p.add_argument("--dry-run", action="store_true", help="预览模式，不实际发布")

    sched_stats_p = sched_sub.add_parser("stats", help="平台频率统计")

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

    elif args.command == "schedule":
        _cmd_schedule(args)


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


def _cmd_schedule(args):
    """调度命令分派"""
    from .scheduler import PipelineScheduler

    config = PipelineConfig.load()
    pipeline = Pipeline(config)
    registry = create_default_registry()
    for name, pub in registry.all().items():
        pipeline.register_publisher(name, pub)
    scheduler = PipelineScheduler(config=config, pipeline=pipeline, registry=registry)
    scheduler.load_state()

    if args.sched_command == "list":
        days = getattr(args, "days", 7)
        upcoming = scheduler.upcoming_schedule(days=days)
        all_items = scheduler.list_queue()
        print(f"\n📅 发布队列 (未来 {days} 天) — 共 {len(upcoming)} 条待发布，队列共 {len(all_items)} 条:\n")
        if upcoming:
            for item in upcoming:
                icon = {"pending": "⏳", "processing": "🔄", "completed": "✅", "failed": "❌"}.get(item.status, "❓")
                p_label = "🔥" if item.priority >= 10 else ("⭐" if item.priority >= 5 else "  ")
                print(f"  {icon} {p_label} [{item.id}] {item.content_id} → {item.platform}")
                print(f"        ⏰ {item.scheduled_at}  |  重试 {item.retry_count}/{item.max_retries}")
                if item.last_error:
                    print(f"        ❌ {item.last_error}")
                print()
        else:
            print("  (空)\n")
        print()

    elif args.sched_command == "add":
        scheduled_at = None
        if args.at:
            try:
                dt = datetime.strptime(args.at, "%Y-%m-%d %H:%M")
                scheduled_at = dt.isoformat()
            except ValueError:
                print(f"\n❌ 日期格式错误: {args.at}")
                print("   请使用格式: YYYY-MM-DD HH:MM (例如 2026-06-01 09:00)\n")
                return

        item = scheduler.enqueue(
            content_id=args.content_id,
            scheduled_at=scheduled_at,
            priority=args.priority,
            platform=args.platform,
        )
        if item:
            print(f"\n✅ 已加入队列: [{item.id}] {item.content_id} → {item.platform}")
            if scheduled_at:
                print(f"   ⏰ 计划时间: {scheduled_at}")
            if item.priority:
                print(f"   🔥 优先级: {item.priority}")
            print()
        else:
            print(f"\n❌ 加入队列失败: 内容 '{args.content_id}' 不存在或已在队列中\n")

    elif args.sched_command == "run":
        dry_run = getattr(args, "dry_run", False)
        if dry_run:
            print("\n🔍 预览模式 (dr run) — 不会实际发布\n")

        result = scheduler.process_queue(dry_run=dry_run)

        print(f"\n📤 队列处理结果:\n")
        if result["published"]:
            print(f"  ✅ 已发布 ({len(result['published'])} 条):")
            for r in result["published"]:
                url = f" → {r.get('url')}" if r.get("url") else ""
                print(f"      {r['content_id']} → {r['platform']}{url}")
        if result["retried"]:
            print(f"  🔄 重试成功 ({len(result['retried'])} 条):")
            for r in result["retried"]:
                url = f" → {r.get('url')}" if r.get("url") else ""
                print(f"      {r['content_id']} → {r['platform']}{url}")
        if result["rate_limited"]:
            print(f"  🚫 频率限制 ({len(result['rate_limited'])} 条):")
            for r in result["rate_limited"]:
                print(f"      {r['content_id']} → {r['platform']} ({r['reason']})")
        if result["failed"]:
            print(f"  ❌ 失败 ({len(result['failed'])} 条):")
            for r in result["failed"]:
                retry_info = f" [重试 {r.get('retry_count', '?')}]" if r.get("will_retry") else " [已达最大重试]"
                print(f"      {r['content_id']} → {r['platform']}: {r['error']}{retry_info}")
        if not any(result.values()):
            print("  (没有需要处理的项)\n")
        print()

    elif args.sched_command == "stats":
        stats = scheduler.get_platform_stats()
        print(f"\n📊 平台频率统计:\n")
        for platform, s in stats.items():
            day_pct = f"{s['daily_used']}/{s['daily_limit']}" if s['daily_limit'] else "∞"
            week_pct = f"{s['weekly_used']}/{s['weekly_limit']}" if s['weekly_limit'] else "∞"
            print(f"  {'📕' if platform == 'xiaohongshu' else '🐦' if platform == 'twitter' else '💼' if platform == 'linkedin' else '📄'} {platform}")
            print(f"      今日: {day_pct}  |  本周: {week_pct}")
        print()

    else:
        print("Usage: pipeline schedule {list,add,run,stats} ...")


if __name__ == "__main__":
    main()

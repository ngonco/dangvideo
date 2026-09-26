import argparse
import asyncio
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from automation.browser_engine import browser_engine
from automation.workflow_manager import workflow_mgr


async def main() -> int:
    parser = argparse.ArgumentParser(description="Thử đăng lại các kênh được chọn cho một video")
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument("--platforms", nargs="+", required=True)
    parser.add_argument("--schedule-time", default=None)
    parser.add_argument("--target-date", default=None)
    parser.add_argument("--allow-repost", action="store_true")
    args = parser.parse_args()

    try:
        result = await workflow_mgr.publish_video_to_platforms(
            args.video_id,
            target_platforms=args.platforms,
            schedule_time=args.schedule_time,
            target_date=args.target_date,
            allow_repost=args.allow_repost,
            enforce_ig_gap=True,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        details = result.get("details") or {}
        failed = [name for name, value in details.items() if not value.get("success")]
        return 1 if failed or not result.get("success") else 0
    finally:
        await browser_engine.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

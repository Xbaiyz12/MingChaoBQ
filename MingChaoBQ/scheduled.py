"""每日定时重建索引：手动往目录加的图、API 保存的新图都要重扫才会进索引。"""

from datetime import datetime

from gsuid_core.aps import scheduler
from gsuid_core.logger import logger

from .utils.paths import INDEX_PATH
from .index_generator import count_pics, rebuild_index
from .mingchao_config import get_int, get_bool


def _target_minutes() -> int:
    """配置里的目标时刻换算成当天第几分钟，越界值夹回合法范围。"""
    hour = min(23, max(0, get_int("mcbq_index_update_hour", 4)))
    minute = min(59, max(0, get_int("mcbq_index_update_minute", 0)))
    return hour * 60 + minute


def _updated_today(now: datetime) -> bool:
    """索引今天已更新过就跳过；手动 bq更新索引 也算，不会重复重扫。"""
    if not INDEX_PATH.exists():
        return False
    return datetime.fromtimestamp(INDEX_PATH.stat().st_mtime).date() == now.date()


@scheduler.scheduled_job("cron", minute="*")
async def auto_update_index() -> None:
    """每分钟看一眼：过了设定时刻且今天还没更新就重建一次，半夜停机错过也会补上。"""
    if not get_bool("mcbq_index_auto_update"):
        return

    now = datetime.now()
    if now.hour * 60 + now.minute < _target_minutes() or _updated_today(now):
        return

    index = await rebuild_index()
    logger.info(f"[MingChaoBQ·索引] 每日自动更新完成，共 {count_pics(index)} 张")

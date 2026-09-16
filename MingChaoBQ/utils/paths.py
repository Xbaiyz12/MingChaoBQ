from pathlib import Path
from gsuid_core.data_store import get_res_path

# 插件数据根目录：gsuid_core/data/MingChaoBQ/
# get_res_path 会自动创建不存在的文件夹
BQ_ROOT = get_res_path("MingChaoBQ")

# 索引文件路径
INDEX_PATH = BQ_ROOT / "index.json"

# 支持的图片格式
SUPPORTED_EXTS = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
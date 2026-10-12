from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsStrConfig,
    GsBoolConfig,
    GsListStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    # ===== 基础 =====
    "mcbq_enable": GsBoolConfig(
        title="启用鸣潮表情包插件",
        desc="总开关，关闭后所有群都无法使用本插件",
        data=True,
    ),
    "mcbq_whitelist_enable": GsBoolConfig(
        title="启用群白名单",
        desc="开启后，只有白名单中的群才能使用本插件",
        data=False,
    ),
    "mcbq_whitelist": GsListStrConfig(
        title="群白名单",
        desc="允许使用本插件的群号，一行一个",
        data=[],
    ),
    "mcbq_blacklist": GsListStrConfig(
        title="群黑名单",
        desc="禁止使用本插件的群号，一行一个。优先级高于白名单",
        data=[],
    ),
    "mcbq_char_alias": GsListStrConfig(
        title="角色别名",
        desc="每行一个角色，格式：角色名:别名1,别名2。例：爱弥斯:小爱,小爱弥斯",
        data=[],
    ),
    # ===== 帮助图素材 =====
    "mcbq_banner_bg": GsStrConfig(
        title="帮助图顶部横幅",
        desc="放在 gsuid_core/data/MingChaoBQ/ 下的图片文件名，留空则使用默认",
        data="",
    ),
    "mcbq_help_bg": GsStrConfig(
        title="帮助图主体背景",
        desc="放在 gsuid_core/data/MingChaoBQ/ 下的图片文件名，留空则使用默认",
        data="",
    ),
    "mcbq_image_max_width": GsStrConfig(
        title="图片最大宽度",
        desc="帮助图超过此宽度会被等比例缩小，默认1200",
        data="1200",
    ),
    # ===== API =====
    "mcbq_api_enable": GsBoolConfig(
        title="启用 API 优先",
        desc="开启后所有指令优先从 API 获取，失败时回退本地",
        data=False,
    ),
    "mcbq_api_timeout": GsStrConfig(
        title="API 等待上限（秒）",
        desc="超过这个时间还没拿到 API 图就立刻改用本地，避免戳一戳/随机表情卡住；填 0 表示不限制，默认3",
        data="3",
    ),
    "mcbq_api_base": GsStrConfig(
        title="API 地址",
        desc="默认 https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games",
        data="https://emoji.wuwa.games/apis/api.random-emoji.wuwa.games",
    ),
    "mcbq_api_token": GsStrConfig(
        title="API Token",
        desc="从表情包网站获取的 Token，用于长期稳定访问",
        data="",
    ),
    "mcbq_api_random_path": GsStrConfig(
        title="随机接口路径",
        desc="拼接在 API 地址后面，默认 /v1alpha1/random",
        data="/v1alpha1/random",
    ),
    "mcbq_api_character_param": GsStrConfig(
        title="角色参数名",
        desc="按角色查询时的参数名，默认 character",
        data="character",
    ),
    "mcbq_api_save_local": GsBoolConfig(
        title="API 结果保存到本地",
        desc="从 API 获取的表情保存到 data/MingChaoBQ/API/角色名/ 下，可去重",
        data=True,
    ),
    # ===== 内置表情包 =====
    "mcbq_builtin_auto_fetch": GsBoolConfig(
        title="自动下载内置表情包",
        desc="首次更新索引时自动下载内置素材（约 143MB），让图库不再是 0 张；关掉可用 bq下载表情包 手动拉取",
        data=True,
    ),
    "mcbq_builtin_pack_url": GsStrConfig(
        title="内置表情包地址",
        desc="留空使用默认的 GitHub Release 地址；换成国内镜像时填直链 zip",
        data="",
    ),
    # ===== 呜哇小站接口 =====
    "mcbq_site_enable": GsBoolConfig(
        title="启用小站接口",
        desc="开启后可用 bq网站搜索 / bq画师列表 / bq拉取角色 等（呜哇小站免费表情包仓库），关闭则全部停用",
        data=True,
    ),
    "mcbq_site_fetch_max": GsStrConfig(
        title="单次拉取上限（张）",
        desc="bq拉取角色 / bq拉取画师 / bq拉取表情包 一次最多拉多少张，默认100，填 0 表示不限制",
        data="100",
    ),
    "mcbq_site_random_fallback": GsBoolConfig(
        title="本地没有时向小站取图",
        desc="bq随机表情 在本地找不到时，直接用关键词向小站要一张（按角色或画师），关掉则只给提示",
        data=True,
    ),
    # ===== 戳一戳 =====
    "mcbq_poke_enable": GsBoolConfig(
        title="启用戳一戳随机表情",
        desc="开启后，用户戳机器人会随机发送一张表情",
        data=True,
    ),
    "mcbq_poke_group_roles": GsListStrConfig(
        title="群专属戳一戳角色",
        desc="格式：群号:角色名，一行一个。例：123456789:爱弥斯",
        data=[],
    ),
    "mcbq_poke_set_pm": GsStrConfig(
        title="设置戳一戳角色的最低权限",
        desc="0=主人 1=超级用户 2=群主 3=管理员 6=所有人，默认3",
        data="3",
    ),
    # ===== 连发与管理 =====
    "mcbq_burst_forward": GsBoolConfig(
        title="连发表情合并转发",
        desc="开启后，连发表情将合并为聊天记录发送，避免刷屏；失败自动降级单发",
        data=True,
    ),
    "mcbq_upload_pm": GsStrConfig(
        title="添加表情的最低权限",
        desc="0=主人 1=超级用户 2=群主 3=管理员 6=所有人，默认0",
        data="0",
    ),
    # ===== 索引 =====
    "mcbq_index_auto_update": GsBoolConfig(
        title="每日自动更新索引",
        desc="每天在设定时间重扫一次表情包目录；手动往目录加图、或 API 保存新图后靠它进索引",
        data=True,
    ),
    "mcbq_index_update_hour": GsStrConfig(
        title="自动更新索引·小时",
        desc="0-23，默认 4（凌晨 4 点）",
        data="4",
    ),
    "mcbq_index_update_minute": GsStrConfig(
        title="自动更新索引·分钟",
        desc="0-59，默认 0",
        data="0",
    ),
}

from typing import Dict
from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsListStrConfig,
    GsStrConfig,
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
}
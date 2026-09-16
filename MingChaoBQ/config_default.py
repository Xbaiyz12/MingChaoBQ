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
        desc="给角色添加别名，格式：别名=真名，一行一个。例：小爱=爱弥斯",
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
    # ===== API 同步 =====
    "mcbq_api_url": GsStrConfig(
        title="API 地址",
        desc="表情包网站 API 的 base URL，例：https://xxx.com",
        data="",
    ),
    "mcbq_api_token": GsStrConfig(
        title="API Token",
        desc="如果需要认证就填，不需要留空",
        data="",
    ),
    "mcbq_api_list_path": GsStrConfig(
        title="列表接口路径",
        desc="拼接在 base URL 后面，例：/api/list 或 /emotions",
        data="/list",
    ),
    "mcbq_api_method": GsStrConfig(
        title="请求方式",
        desc="GET 或 POST",
        data="GET",
    ),
    "mcbq_api_data_path": GsStrConfig(
        title="数据数组路径",
        desc="JSON 里数据数组的位置，用点分隔。例：data 或 data.list。留空则整个响应就是数组",
        data="",
    ),
    "mcbq_api_artist_field": GsStrConfig(
        title="画师字段名",
        desc="JSON 里画师名的字段，例：artist",
        data="artist",
    ),
    "mcbq_api_char_field": GsStrConfig(
        title="角色字段名",
        desc="JSON 里角色名的字段，例：character",
        data="character",
    ),
    "mcbq_api_name_field": GsStrConfig(
        title="表情字段名",
        desc="JSON 里表情名的字段，例：name",
        data="name",
    ),
    "mcbq_api_url_field": GsStrConfig(
        title="图片地址字段名",
        desc="JSON 里图片 URL 的字段，例：url",
        data="url",
    ),
    "mcbq_api_headers": GsListStrConfig(
        title="额外请求头",
        desc="一行一个 Key: Value，例：Referer: https://xxx.com",
        data=[],
    ),
    "mcbq_api_sync_hour": GsStrConfig(
        title="定时同步小时",
        desc="每天几点自动同步，默认 4 表示凌晨 4 点",
        data="4",
    ),
}
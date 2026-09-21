"""帮助图数据结构，对应框架 get_new_help 实际读取的字段。"""

from typing import TypedDict

from PIL import Image


class HelpSVRequired(TypedDict):
    name: str
    eg: str


class HelpSV(HelpSVRequired, total=False):
    """一条命令。icon 解析不到时会缺这个键。"""

    icon: Image.Image


class HelpCategoryRequired(TypedDict):
    """框架按 sv["desc"] / sv["data"] 直取，必须给全。"""

    desc: str
    data: list[HelpSV]


class HelpCategory(HelpCategoryRequired, total=False):
    """一个分类卡片。pm 存在时框架会按用户权限决定是否隐藏。"""

    name: str
    help: str
    color: str
    pm: int
    icon: Image.Image

"""表情包索引的数据结构。索引树与 pic 元信息的唯一类型来源。"""

from typing import TypedDict


class PicInfo(TypedDict):
    """索引里存的最小信息：文件相对路径 + 表情名。"""

    file: str
    emotion: str


class PicEntry(PicInfo, total=False):
    """检索时临时补上 _artist / _char / _sub，API 来源的图带 source="api"。"""

    source: str
    _artist: str
    _char: str
    _sub: str


SubCats = dict[str, list[PicEntry]]
CharMap = dict[str, SubCats]
# {画师: {角色: {子分类: [pic, ...]}}}
Index = dict[str, CharMap]

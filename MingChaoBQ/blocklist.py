"""屏蔽词匹配：命中任一关键词的网站表情不拉取、不发送。"""

from .mingchao_config import get_str_list


def blocked_keywords() -> list[str]:
    """当前生效的屏蔽词：去空白、转小写、去重保序。"""
    words: list[str] = []
    for item in get_str_list("mcbq_block_list"):
        word = item.strip().casefold()
        if word and word not in words:
            words.append(word)
    return words


def is_blocked(*texts: str) -> bool:
    """任一文本包含任一屏蔽词即算命中；没有配置屏蔽词时一律放行。"""
    words = blocked_keywords()
    if not words:
        return False
    joined = " ".join(item for item in texts if item).casefold()
    if not joined:
        return False
    return any(word in joined for word in words)

"""首页嵌入会话在 OmniDB / RedisInsight 中使用的临时连接命名约定。"""

TEMP_EXTERNAL_ALIAS_PREFIX = "__qn_tmp_"


def is_temp_external_alias(name: str) -> bool:
    return (name or "").startswith(TEMP_EXTERNAL_ALIAS_PREFIX)

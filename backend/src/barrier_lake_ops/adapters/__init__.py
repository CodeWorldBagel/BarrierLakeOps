"""外部資料源 adapter:每個資料源一個 adapter,失敗時明確降級(不捏造資料)。"""


class AdapterError(Exception):
    """外部資料源不可用 / 回應異常。呼叫端據此降級。"""

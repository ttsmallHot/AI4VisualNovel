"""
Agent Message Protocol
~~~~~~~~~~~~~~~~~~~~~~
统一 Agent 间通信格式：
- name: 发送者名称
- content: 结构化 JSON 对象（Python dict）
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Msg:
    """统一消息对象（name + content）"""

    name: str
    content: Dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("消息字段 name 必须是非空字符串")
        if not isinstance(self.content, dict):
            raise ValueError("消息字段 content 必须是 JSON 对象（dict）")
        self.name = self.name.strip()

    @classmethod
    def from_payload(cls, name: str, payload: Any) -> "Msg":
        if isinstance(payload, dict):
            content = payload
        else:
            content = {"value": payload}
        return cls(name=name, content=content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "content": self.content
        }


class MessageProtocol:
    """轻量消息协议工具（name + content）"""

    @staticmethod
    def create(name: str, content: Dict[str, Any]) -> Dict[str, Any]:
        return Msg(name=name, content=content).to_dict()

    @staticmethod
    def normalize_content(content: Any) -> Dict[str, Any]:
        """将任意 payload 规范为 JSON 对象。"""
        if isinstance(content, dict):
            return content
        return {"value": content}

    @classmethod
    def from_output(cls, name: str, output: Any) -> Dict[str, Any]:
        """从 Agent 原始输出构建标准消息。"""
        return Msg.from_payload(name=name, payload=output).to_dict()

    @staticmethod
    def validate(message: Dict[str, Any]) -> bool:
        """验证消息结构是否符合 name + content 协议。"""
        try:
            Msg(name=message.get("name"), content=message.get("content"))
            return True
        except Exception:
            return False

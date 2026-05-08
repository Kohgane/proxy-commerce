"""Phase 138 — 다채널 인바운드 어댑터."""
from .base import InboundMessage, InboundChannelAdapter
from .email_imap import EmailImapAdapter
from .coupang_qa import CoupangQAAdapter
from .naver_talk import NaverTalkAdapter
from .eleven_qa import ElevenQAAdapter

__all__ = [
    "InboundMessage",
    "InboundChannelAdapter",
    "EmailImapAdapter",
    "CoupangQAAdapter",
    "NaverTalkAdapter",
    "ElevenQAAdapter",
]

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint

from .base import Base, Column


class UserMessageOutbox(Base):
    __tablename__ = "user_message_outbox"

    # UUID (string) to simplify cross-db compatibility and external ack.
    id = Column(String(255), primary_key=True)

    user_id = Column(String(255), index=True, nullable=False)
    channel = Column(String(50), nullable=False, default="wechat")
    message_type = Column(String(50), nullable=False, default="daily_digest")

    # Digest metadata (optional for other message types).
    digest_date = Column(String(10), index=True)  # YYYY-MM-DD
    digest_slot = Column(String(20), index=True)  # morning|afternoon|evening|daily
    start_ts = Column(Integer)
    end_ts = Column(Integer)

    title = Column(String(255))
    message_text = Column(Text, nullable=False)
    payload_json = Column(Text)

    # 0: pending, 1: sent, 9: failed
    status = Column(Integer, default=0)
    error = Column(Text)
    sent_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "channel",
            "message_type",
            "digest_date",
            "digest_slot",
            name="uq_user_message_outbox_user_key",
        ),
    )


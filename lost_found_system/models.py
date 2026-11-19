"""
models.py - Data structures for the Lost and Found System
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Item:
    id: Optional[int] = None
    title: str = ""
    category: str = "Others"
    item_type: str = "lost"  # 'lost' or 'found'
    description: str = ""
    location: str = ""
    date_reported: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    reporter_name: str = ""
    reporter_contact: str = ""
    status: str = "Open"  # Open, Matched, Claimed, Returned
    reward: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "item_type": self.item_type,
            "description": self.description,
            "location": self.location,
            "date_reported": self.date_reported,
            "reporter_name": self.reporter_name,
            "reporter_contact": self.reporter_contact,
            "status": self.status,
            "reward": self.reward,
            "created_at": self.created_at
        }

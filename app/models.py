"""Data models shared across the app."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Segment:
    """A single transcribed chunk with timing."""
    start: float
    end: float
    text: str


@dataclass
class Project:
    id: Optional[int]
    name: str
    source_type: str          # "local" | "youtube" | "gdrive"
    source_url: str           # original path or URL
    video_path: str           # resolved local file path
    whisper_model: str = "small"
    transcript_json: str = ""  # JSON-encoded list[Segment]
    status: str = "new"        # new -> transcribed -> analyzed -> exported
    created_at: str = ""


@dataclass
class Topic:
    id: Optional[int]
    project_id: int
    mode: str
    name: str
    text: str
    start: float
    end: float
    duration: float
    selected: bool = True
    order_index: int = 0


@dataclass
class TextBox:
    text: str
    x: int
    y: int
    font_size: int = 32
    font_color: str = "#FFFFFF"
    font_family: str = "Arial"


@dataclass
class Template:
    id: Optional[int]
    name: str
    image_path: str
    canvas_w: int
    canvas_h: int
    video_x: int
    video_y: int
    video_w: int
    video_h: int
    text_boxes: list = field(default_factory=list)  # list[TextBox]

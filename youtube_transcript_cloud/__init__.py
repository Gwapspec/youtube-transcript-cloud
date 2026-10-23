"""YouTube transcripts that work from cloud servers (AWS, Google Cloud, Azure, Colab, Lambda).

YouTube blocks most cloud-provider IPs, so libraries that call YouTube directly often fail in
production. This client sends the request to the hosted YouTube Transcript Scraper on Apify
(https://apify.com/honestdata/youtube-transcript-scraper), which tries a data-center IP first and
moves to a residential one when YouTube refuses. $0.002 per transcript on Apify's free-plan pricing;
videos without a transcript are free.

    from youtube_transcript_cloud import TranscriptClient
    client = TranscriptClient()          # reads APIFY_TOKEN
    t = client.fetch("jNQXAC9IVRw")
    print(t.text)
"""
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Union

__version__ = "0.1.0"
__all__ = ["TranscriptClient", "Transcript", "Snippet", "TranscriptError", "TranscriptUnavailable", "video_id"]

ACTOR = "honestdata~youtube-transcript-scraper"
ENDPOINT = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
BATCH = 50  # videos per cloud run; a sync run must finish within Apify's 300-second limit
_VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")


class TranscriptError(Exception):
    """The request failed: missing or wrong token, a timeout, or an error from Apify."""


class TranscriptUnavailable(TranscriptError):
    """The video has no transcript we can deliver.

    `reason` is one of: no_captions, language_not_available, private, unavailable, age_restricted,
    members_only, region_blocked, paid, live_not_started, and a few more (see the tool's README).
    You are not charged for these videos.
    """

    def __init__(self, video_id: Optional[str], reason: Optional[str], message: Optional[str]):
        super().__init__(f"{video_id}: {reason}: {message}")
        self.video_id, self.reason, self.message = video_id, reason, message


@dataclass
class Snippet:
    text: str
    start: float
    duration: float


@dataclass
class Transcript:
    video_id: str
    language_code: Optional[str]
    language: Optional[str]
    is_generated: Optional[bool]  # True for YouTube's auto-generated captions, False for uploaded ones
    text: str
    snippets: List[Snippet]
    title: Optional[str] = None
    coverage_pct: Optional[float] = None  # share of the video's length with words on screen
    language_matched: Optional[bool] = None  # False when YouTube only had another language
    raw: dict = field(default_factory=dict, repr=False)  # the full result row

    def to_raw_data(self) -> List[dict]:
        """The same list of {"text", "start", "duration"} that youtube-transcript-api returns."""
        return [{"text": s.text, "start": s.start, "duration": s.duration} for s in self.snippets]

    def __iter__(self) -> Iterator[Snippet]:
        return iter(self.snippets)

    def __len__(self) -> int:
        return len(self.snippets)


def video_id(url_or_id: str) -> str:
    """The 11-character id from a watch, youtu.be, shorts, embed or live URL, or from a bare id."""
    m = _VIDEO_ID.search(url_or_id.strip())
    if not m:
        raise ValueError(f"not a YouTube video URL or id: {url_or_id!r}")
    return m.group(1) or m.group(2)


def _transcript(row: dict) -> Transcript:
    if not row.get("transcriptAvailable"):
        raise TranscriptUnavailable(row.get("videoId"), row.get("unavailableReason"), row.get("unavailableMessage"))
    caption = (row.get("captionType") or "").lower()
    return Transcript(
        video_id=row.get("videoId") or "",
        language_code=row.get("languageCode"),
        language=row.get("language"),
        is_generated=caption.startswith("auto") if caption else None,
        text=row.get("text") or "",
        snippets=[Snippet(s.get("text") or "", float(s.get("start") or 0), float(s.get("duration") or 0))
                  for s in row.get("segments") or []],
        title=row.get("title"),
        coverage_pct=row.get("coveragePct"),
        language_matched=row.get("languageMatched"),
        raw=row,
    )


class TranscriptClient:
    """Fetch transcripts through Apify. Each call is one cloud run (about 10-20 seconds); batch with fetch_many."""

    def __init__(self, token: Optional[str] = None, language: str = "en", fallback_to_other_language: bool = True,
                 timeout: int = 300):
        self.token = token or os.environ.get("APIFY_TOKEN")
        if not self.token:
            raise TranscriptError("No Apify token: set APIFY_TOKEN or pass token=. A free account's token is under "
                                  "console.apify.com > Settings > API & Integrations.")
        self.language, self.fallback, self.timeout = language, fallback_to_other_language, timeout

    def _input(self, language: Optional[str], **extra) -> dict:
        return {"language": language or self.language, "fallbackToOtherLanguage": self.fallback, **extra}

    def _run(self, payload: dict) -> List[dict]:
        url = ENDPOINT.format(actor=ACTOR) + f"?timeout={self.timeout}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.token}",
                                              "User-Agent": f"youtube-transcript-cloud/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout + 30) as r:
                rows = json.load(r)
        except urllib.error.HTTPError as e:
            raise TranscriptError(f"Apify answered HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
        except urllib.error.URLError as e:
            raise TranscriptError(f"Could not reach Apify: {e.reason}") from None
        if not isinstance(rows, list):
            raise TranscriptError(f"Unexpected answer from Apify: {str(rows)[:300]}")
        return rows

    def fetch(self, video: str, language: Optional[str] = None) -> Transcript:
        """One video, by URL or id. Raises TranscriptUnavailable if it has no transcript."""
        vid = video_id(video)
        rows = self._run(self._input(language, videos=[f"https://www.youtube.com/watch?v={vid}"]))
        row = next((r for r in rows if r.get("videoId") == vid), rows[0] if rows else None)
        if row is None:
            raise TranscriptError(f"{vid}: the run returned no result")
        return _transcript(row)

    def fetch_many(self, videos: Iterable[str], language: Optional[str] = None
                   ) -> Dict[str, Union[Transcript, TranscriptUnavailable]]:
        """Many videos in as few runs as possible: {video_id: Transcript or TranscriptUnavailable}."""
        ids = list(dict.fromkeys(video_id(v) for v in videos))
        out: Dict[str, Union[Transcript, TranscriptUnavailable]] = {}
        for i in range(0, len(ids), BATCH):
            urls = [f"https://www.youtube.com/watch?v={v}" for v in ids[i:i + BATCH]]
            for row in self._run(self._input(language, videos=urls)):
                try:
                    out[row.get("videoId")] = _transcript(row)
                except TranscriptUnavailable as e:
                    out[row.get("videoId")] = e
        return out

    def fetch_channel(self, channel: str, max_videos: int = 15, only_new: bool = False,
                      language: Optional[str] = None) -> Dict[str, Union[Transcript, TranscriptUnavailable]]:
        """A channel URL, @handle or playlist: its newest videos (up to 15 per run).

        only_new=True returns only videos that earlier only_new runs with the same settings didn't
        deliver, so a daily job pays only for new uploads.
        """
        rows = self._run(self._input(language, channels=[channel], maxVideosPerChannel=max_videos,
                                     onlyNewVideos=only_new))
        out: Dict[str, Union[Transcript, TranscriptUnavailable]] = {}
        for row in rows:
            try:
                out[row.get("videoId")] = _transcript(row)
            except TranscriptUnavailable as e:
                out[row.get("videoId")] = e
        return out

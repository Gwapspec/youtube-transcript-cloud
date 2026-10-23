# youtube-transcript-cloud

**YouTube transcripts that work from cloud servers:** AWS, Google Cloud, Azure, Colab, Lambda, Render, Railway.

**The problem:**
- Libraries that call YouTube directly work on a laptop, then fail on a server with errors like
  `RequestBlocked`, `IpBlocked` or "YouTube is blocking requests from your IP".
- The popular [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) explains why
  in its README: YouTube blocks most IPs that belong to cloud providers. It recommends rotating
  residential proxies.

**This client** sends the request to a hosted tool instead:
- The [YouTube Transcript Scraper](https://apify.com/honestdata/youtube-transcript-scraper) on Apify
  handles the proxies.
- It tries a data-center IP first and moves to a residential one when YouTube refuses.
- It returns the same timed snippets, plus the facts you need before you trust a transcript.

```bash
pip install git+https://github.com/Gwapspec/youtube-transcript-cloud
export APIFY_TOKEN=...   # free account: console.apify.com > Settings > API & Integrations
```

```python
from youtube_transcript_cloud import TranscriptClient

client = TranscriptClient()
t = client.fetch("https://www.youtube.com/watch?v=jNQXAC9IVRw")
print(t.text)
for s in t.snippets:
    print(f"{s.start:7.2f}s  {s.text}")
```

## Coming from youtube-transcript-api

```python
# before
from youtube_transcript_api import YouTubeTranscriptApi
data = YouTubeTranscriptApi().fetch(video_id).to_raw_data()

# after: the same list of {"text", "start", "duration"}
from youtube_transcript_cloud import TranscriptClient
data = TranscriptClient().fetch(video_id).to_raw_data()
```

## Many videos, channels and playlists

```python
results = client.fetch_many(["jNQXAC9IVRw", "https://youtu.be/dQw4w9WgXcQ"])   # one cloud run per 50 videos
for vid, r in results.items():
    print(vid, r.text[:80] if hasattr(r, "text") else f"no transcript: {r.reason}")

# A daily job that pays only for new uploads:
new = client.fetch_channel("@NASA", max_videos=15, only_new=True)
```

## What you get besides the text

| Field | Why it matters |
|---|---|
| `is_generated` | Auto captions come from speech recognition and miss names, numbers and jargon. Label them before an AI reads them. |
| `language_code`, `language_matched` | `False` when YouTube only had another language. |
| `coverage_pct` | How much of the video has words on screen. A low number means music or missing pieces. |
| `TranscriptUnavailable.reason` | Why there's no transcript: `no_captions`, `private`, `members_only`, `age_restricted`, `region_blocked`... |
| `raw` | The full result row, including the title, channel, duration and view count. |

## Cost

- **$0.002 per transcript** on Apify's free-plan pricing, less on paid plans.
- **Videos without a transcript are free.**
- **Apify's free plan** includes a monthly usage credit. At this price it covers roughly 2,500
  transcripts a month.
- **Speed:** each call starts a cloud run of about 10-20 seconds. Use `fetch_many` for batches.

## Errors

| Error | When |
|---|---|
| `TranscriptUnavailable` | The video has no transcript we can deliver. Check `.reason`. You're not charged. |
| `TranscriptError` | Missing or wrong token, a timeout, or an error from Apify |

## Notes

- This is an independent project. It isn't affiliated with YouTube, Google or youtube-transcript-api.
- Transcripts belong to their creators. Check YouTube's terms for your use.
- **Disclosure:** made by Honest Data, which sells the hosted tool this client calls. The client is
  free and MIT-licensed.

Questions or bugs: [open an issue](https://github.com/Gwapspec/youtube-transcript-cloud/issues).

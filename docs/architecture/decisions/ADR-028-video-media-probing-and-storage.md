# ADR-028: Video media probing and storage

Status: Accepted for Feature Phase 5 Session 06 (2026-11-18); live acceptance pending.

## Context

Reels need bounded validation and storage before publishing exists. Untrusted video is larger and exposes complex parsers. Images must retain their image-only contracts. The specification and conflicts are recorded in [platform capabilities](../../research/platform-capabilities.md#reel-video-specification--feature-phase-5-session-06).

## Decision

Use Debian `ffmpeg` (both ffprobe and ffmpeg) pinned by `ARG FFMPEG_DEBIAN_VERSION=7:5.1.9-0+deb12u1` in the backend stage of `python:3.12-slim-bookworm`, installed as root before `USER pivoris:pivoris`. The build checks `dpkg-query -W -f='${Version}' ffmpeg` equals the ARG. Pin source supplied by the session lead: https://packages.debian.org/bookworm/ffmpeg and https://security-tracker.debian.org/tracker/source-package/ffmpeg, accessed 2026-11-18.

No transcoding. Store the original bytes with their SHA-256. Our bounded seek-based ISO BMFF scanner validates box sizes, `ftyp` major brand, moov-first and edit-list presence before ffprobe. Maximum 256 top-level boxes, 4096 nested boxes, depth cap 4 and 32 MiB moov inspection. Probe optional JSON defensively; apply phone display rotation before size/aspect rules. Fake header fixtures and deterministic Pillow thumbnails support offline tests. `VIDEO_PROBER=fake` is forbidden in production startup and `check-config --production`.

Subprocesses use argument arrays, no shell, no stdin, only PATH and LC_ALL=C, private scratch directories, local file protocol whitelist and forced MOV/MP4-family demuxer. The command uses `-f mov`, the canonical ffmpeg 5.1 alias for the demuxer whose displayed format_name is `mov,mp4,m4a,3gp,3g2,mj2`; the comma-separated display name is not passed as a CLI format argument. The box scanner separately rejects 3GP/3G2/M4A/MJ2 brands. They cannot open HLS/concat/network protocols. Wall timeouts kill the POSIX process group. POSIX rlimits: CPU timeout+5 seconds, 2 GiB address space, 1 MiB probe / 16 MiB thumbnail file size, 64 descriptors, no core dump. Windows skips rlimits and relies on timeout. A process-wide semaphore defaults to 2 concurrent binary calls with a 3-second wait before retryable 503. Only thumbnail extraction invokes decoders. Residual risk includes vulnerabilities in those codecs/demuxers; the Debian tracker lists roughly 136 open/postponed bookworm ffmpeg issues as of the supplied research (mostly unrelated codecs/demuxers); restrictions reduce exposure without proving safety.

Assets have `image`, `video`, `video_thumbnail` kinds. A thumbnail is a separately stored baseline sRGB JPEG produced by the existing image sanitizer, linked through a workspace composite FK. Video quota is 2 GiB/workspace including thumbnails; real-size quota decisions serialize on the workspace row. Body-size rejection precedes multipart parsing: a Content-Length above the cap plus 64 KiB, or a missing/invalid one (chunked), is refused with 413 before any body byte is read, because Starlette spools the multipart body to disk before application code can count it; streaming counting enforces the real per-file cap. Video and thumbnail objects are stored before a single transaction creates both rows; failure rolls back and removes both. Storage and probing never run in a DB transaction. Authenticated content endpoints serve all kinds; S3 open delegates chunked reads instead of buffering whole objects. HTTP Range is deferred to Session 07.

## Alternatives

- Static builds with a checksum: reproducible, but do not receive Debian's distro security patch process.
- PyAV or imageio-ffmpeg wheels: another binary supply chain and patching policy, no benefit for this bounded subprocess interface.
- Lossless remux: `-c copy -map_metadata -1 -movflags +faststart` could remove GPS, repair atom ordering and normalize edit lists without transcoding. Follow-up question: offer it explicitly or require owner exports? Not implemented here.
- Transcoding: resource cost, quality changes and asynchronous processing are outside Session 06.

## Consequences and open verification

When Debian replaces deb12u1 with deb12u2, the old mirror pin may disappear and builds fail loudly. Bump only after reading `apt-cache policy ffmpeg` in the base container, rebuilding and running the packaging/real-binary tests. Extra image size: **to be measured on the first build**. Scratch disk needs about twice the upload size per concurrent upload (Starlette spool plus our copy), plus bounded binary output and thumbnails.

Video QuickTime/EXIF metadata, including GPS in `com.apple.quicktime.location.ISO6709`, is **not stripped**. Originals are private to workspace members; Instagram removing location metadata on publication is unverified. Do not represent it as a privacy guarantee. moov-last is rejected with Fast Start export guidance. Edit lists warn by default; closed GOP and audio bitrate are not verified. Presigned video URL acceptance/lifetime, live Meta processing and cover behavior remain pending. Docker build, actual image-size measurement, local real-ffprobe execution and `caddy validate` are pending in this environment.

Videos use existing ready/deleted states. Until Session 07 introduces Reel references, videos are orphans eligible after 7 days; published-only retention is 90 days. Thumbnails follow their parent, cannot expire while it is live, and crash recovery completes deletion on the next run. Workspace purge deletes rows but not storage objects (pre-existing image behavior with a larger video cost); object purge is an open follow-up.

## Addendum: Reels publishing (Feature Phase 5 Session 07)

Session 07 adds the `reel` content type (migration `0083`), authenticated `Range` / `206` / `416` byte-range streaming on `GET /media/{media_id}/content` (`open_range` on local and S3 storage after DB release), and non-blocking Reel publishing via the `poll_reel_container` backoff job (`15, 30, 60, 60, 120, 120, 180, 180, 300` s up to 30 min `REEL_PROCESSING_TIMEOUT`, `MAX_CONTAINER_RECREATIONS = 2`, 5 read-error tolerance before retry/failover). Live Meta `REELS` acceptance, signed public video URL lifetime/fetch reliability, custom cover vs `thumb_offset_ms` rendering on Instagram, and edit-list playback on Meta remain pending live verification.

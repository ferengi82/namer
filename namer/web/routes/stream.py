"""
Defines the video streaming route of a Flask webserver for namer.

Streams files from ``config.failed_dir`` to a browser ``<video>`` element.
Natively playable formats are served via ``send_file`` with HTTP Range support,
everything else is remuxed to fragmented MP4 via an ``ffmpeg`` subprocess pipe.
"""

import mimetypes
import subprocess
from pathlib import Path
from typing import Iterator

from flask import Blueprint, Response, abort, request, send_file, stream_with_context
from loguru import logger

from namer.configuration import NamerConfig


_NATIVE_BROWSER_EXTS = {'.mp4', '.m4v', '.webm'}


def _resolve_requested_file(file_param: str, config: NamerConfig) -> Path:
    """
    Validate the ``file`` query parameter and return an absolute, resolved
    path that is guaranteed to live inside ``config.failed_dir``.

    Rejects absolute paths, backslashes, directory traversal, symlink escapes,
    and non-file targets with an HTTP error.
    """
    if not file_param:
        abort(400)

    # Reject backslashes to avoid Windows-style escapes sneaking past.
    if '\\' in file_param:
        abort(400)

    candidate = Path(file_param)
    if candidate.is_absolute():
        abort(403)

    failed_root = config.failed_dir.resolve()
    try:
        requested = (failed_root / candidate).resolve()
    except (OSError, RuntimeError):
        abort(400)

    # ``resolve()`` follows symlinks; ``is_relative_to`` on the resolved path
    # catches both ``..`` traversal and symlink escapes out of failed_dir.
    if not requested.is_relative_to(failed_root):
        abort(403)

    if not requested.is_file():
        abort(404)

    return requested


def _iter_ffmpeg_output(ffmpeg_cmd: str, source: Path, start_seconds: float = 0.0) -> Iterator[bytes]:
    """
    Spawn ffmpeg as a subprocess and yield its stdout bytes as a remuxed
    fragmented MP4 stream. The subprocess is killed deterministically when
    the generator is closed (e.g. client disconnect, modal close, exception).
    """
    args = [
        ffmpeg_cmd,
        '-hide_banner',
        '-loglevel', 'error',
    ]
    if start_seconds > 0:
        # Keyframe-accurate seek placed before ``-i`` for fast input seeking.
        args += ['-ss', f'{start_seconds:.3f}']
    args += [
        '-i', str(source),
        '-f', 'mp4',
        '-vcodec', 'copy',
        '-acodec', 'aac',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        '-',
    ]

    logger.debug(f'Starting ffmpeg stream for {source.name}')
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        logger.debug(f'Stopped ffmpeg stream for {source.name}')


def get_routes(config: NamerConfig) -> Blueprint:
    """
    Builds the stream blueprint for flask with passed in context, the NamerConfig.
    """
    blueprint = Blueprint('stream', __name__, url_prefix='/api')

    @blueprint.route('/v1/stream', methods=['GET', 'HEAD'])
    def stream_video() -> Response:
        file_param = request.args.get('file', type=str)
        if file_param is None:
            abort(400)

        requested = _resolve_requested_file(file_param, config)

        suffix = requested.suffix.lower()
        if suffix in _NATIVE_BROWSER_EXTS:
            mime, _ = mimetypes.guess_type(requested.name)
            return send_file(
                requested,
                mimetype=mime or 'application/octet-stream',
                conditional=True,
            )

        # Non-native container: remux through ffmpeg.
        # Extension whitelist guards against arbitrary binary input being
        # fed to ffmpeg; only configured namer target extensions are allowed.
        allowed_exts = {f'.{ext.lower().lstrip(".")}' for ext in (config.target_extensions or [])}
        if allowed_exts and suffix not in allowed_exts:
            abort(415)

        # HEAD: answer without launching ffmpeg. Omitting Content-Length
        # makes Safari fall back to progressive download.
        if request.method == 'HEAD':
            return Response(status=200, mimetype='video/mp4')

        try:
            start_seconds = float(request.args.get('t', default=0.0, type=float) or 0.0)
        except (TypeError, ValueError):
            start_seconds = 0.0

        ffmpeg_cmd = config.ffmpeg.get_ffmpeg_cmd() if config.ffmpeg else 'ffmpeg'
        generator = _iter_ffmpeg_output(ffmpeg_cmd, requested, start_seconds)
        response = Response(stream_with_context(generator), mimetype='video/mp4')
        # Streamed responses must not be compressed; transcoded MP4 is already
        # as small as it will get and gzip would break progressive playback.
        response.headers['Content-Encoding'] = 'identity'
        response.headers['Cache-Control'] = 'no-store'
        return response

    return blueprint

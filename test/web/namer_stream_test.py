"""
Unit tests for the video stream blueprint.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from flask import Flask

from namer.web.routes.stream import get_routes
from test.utils import sample_config


class StreamBlueprintTests(unittest.TestCase):
    """
    Tests the /api/v1/stream endpoint using Flask's test client.
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix='namer_stream_test_'))
        self.failed_dir = self.tmp_dir / 'failed'
        self.failed_dir.mkdir()

        self.config = sample_config()
        self.config.failed_dir = self.failed_dir
        # sample_config() may leave target_extensions empty for the stock
        # config; the stream endpoint whitelist is derived from this.
        if not self.config.target_extensions:
            self.config.target_extensions = ['mp4', 'm4v', 'webm', 'mkv', 'avi', 'mov']

        self.app = Flask(__name__)
        self.app.register_blueprint(get_routes(self.config))
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_fake(self, relative: str, size: int = 1024) -> Path:
        target = self.failed_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'\x00' * size)
        return target

    def test_stream_native_mp4_returns_200(self):
        self._write_fake('clip.mp4', size=2048)
        resp = self.client.get('/api/v1/stream?file=clip.mp4')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_length, 2048)
        self.assertIn(resp.mimetype, ('video/mp4', 'video/x-mp4'))

    def test_stream_native_webm_returns_200(self):
        self._write_fake('clip.webm', size=512)
        resp = self.client.get('/api/v1/stream?file=clip.webm')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_length, 512)

    def test_stream_range_request_returns_206(self):
        self._write_fake('clip.mp4', size=4096)
        resp = self.client.get('/api/v1/stream?file=clip.mp4', headers={'Range': 'bytes=0-99'})
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(len(resp.get_data()), 100)

    def test_stream_missing_file_returns_404(self):
        resp = self.client.get('/api/v1/stream?file=does_not_exist.mp4')
        self.assertEqual(resp.status_code, 404)

    def test_stream_missing_file_param_returns_400(self):
        resp = self.client.get('/api/v1/stream')
        self.assertEqual(resp.status_code, 400)

    def test_stream_traversal_is_rejected(self):
        resp = self.client.get('/api/v1/stream?file=../outside.mp4')
        self.assertEqual(resp.status_code, 403)

    def test_stream_absolute_path_is_rejected(self):
        resp = self.client.get('/api/v1/stream?file=/etc/passwd')
        self.assertEqual(resp.status_code, 403)

    def test_stream_backslash_is_rejected(self):
        resp = self.client.get('/api/v1/stream?file=..\\outside.mp4')
        self.assertEqual(resp.status_code, 400)

    def test_stream_subdirectory_is_allowed(self):
        self._write_fake('subdir/clip.mp4', size=256)
        resp = self.client.get('/api/v1/stream?file=subdir/clip.mp4')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_length, 256)

    def test_stream_symlink_escape_is_rejected(self):
        outside = self.tmp_dir / 'outside.mp4'
        outside.write_bytes(b'\x00' * 64)
        link = self.failed_dir / 'link.mp4'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not supported on this platform')
        resp = self.client.get('/api/v1/stream?file=link.mp4')
        self.assertEqual(resp.status_code, 403)

    def test_stream_unsupported_extension_is_rejected(self):
        self.config.target_extensions = ['mp4']
        self._write_fake('clip.exe', size=128)
        resp = self.client.get('/api/v1/stream?file=clip.exe')
        self.assertEqual(resp.status_code, 415)

    def test_stream_head_native_returns_200(self):
        self._write_fake('clip.mp4', size=2048)
        resp = self.client.head('/api/v1/stream?file=clip.mp4')
        self.assertEqual(resp.status_code, 200)

    def test_stream_head_transcode_returns_200_without_ffmpeg(self):
        self._write_fake('clip.mkv', size=2048)
        with patch('namer.web.routes.stream.subprocess.Popen') as popen_mock:
            resp = self.client.head('/api/v1/stream?file=clip.mkv')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.mimetype, 'video/mp4')
            popen_mock.assert_not_called()

    def test_stream_transcode_invokes_ffmpeg_with_expected_args(self):
        self._write_fake('clip.mkv', size=2048)

        proc_mock = MagicMock()
        # Single chunk then EOF
        proc_mock.stdout.read.side_effect = [b'FAKEMP4DATA', b'']
        proc_mock.poll.return_value = 0
        proc_mock.wait.return_value = 0

        with patch('namer.web.routes.stream.subprocess.Popen', return_value=proc_mock) as popen_mock:
            resp = self.client.get('/api/v1/stream?file=clip.mkv')
            body = resp.get_data()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'video/mp4')
        self.assertIn(b'FAKEMP4DATA', body)
        popen_mock.assert_called_once()
        called_args = popen_mock.call_args[0][0]
        self.assertIn('-vcodec', called_args)
        self.assertIn('copy', called_args)
        self.assertIn('-acodec', called_args)
        self.assertIn('aac', called_args)
        self.assertIn('-f', called_args)
        self.assertIn('mp4', called_args)
        self.assertTrue(any('frag_keyframe' in str(a) for a in called_args))

    def test_stream_transcode_with_seek_uses_ss(self):
        self._write_fake('clip.mkv', size=1024)

        proc_mock = MagicMock()
        proc_mock.stdout.read.side_effect = [b'', b'']
        proc_mock.poll.return_value = 0
        proc_mock.wait.return_value = 0

        with patch('namer.web.routes.stream.subprocess.Popen', return_value=proc_mock) as popen_mock:
            self.client.get('/api/v1/stream?file=clip.mkv&t=12.5')

        called_args = popen_mock.call_args[0][0]
        self.assertIn('-ss', called_args)
        ss_index = called_args.index('-ss')
        self.assertEqual(called_args[ss_index + 1], '12.500')

    def test_stream_transcode_kills_ffmpeg_on_client_disconnect(self):
        self._write_fake('clip.mkv', size=1024)

        proc_mock = MagicMock()
        proc_mock.stdout.read.return_value = b'chunk'
        # First ``poll`` in the finally block returns None (still alive),
        # so ``kill`` must be called.
        proc_mock.poll.return_value = None
        proc_mock.wait.return_value = 0

        with patch('namer.web.routes.stream.subprocess.Popen', return_value=proc_mock):
            resp = self.client.get('/api/v1/stream?file=clip.mkv')
            resp.close()

        proc_mock.kill.assert_called()


if __name__ == '__main__':
    unittest.main()

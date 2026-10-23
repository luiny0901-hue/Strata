"""CPU-only input normalization cache checks; no encoder or GPU is started."""
import hashlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from serve.server import Vision


class SourceCache(unittest.TestCase):
    def make(self, directory, enabled=True):
        v = Vision.__new__(Vision)
        v.dir = Path(directory)
        v.lock = threading.Lock()
        v.cache = {}
        v.source_cache = {} if enabled else None
        v.proc = SimpleNamespace(stdin=io.StringIO())
        v._readline = lambda *args: 'OK 4'
        return v

    def test_repeated_raw_bytes_skip_conversion_only_when_enabled(self):
        for enabled in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                v = self.make(directory, enabled)
                with patch.object(Vision, 'normalize', side_effect=lambda data: b'PNG'+data) as normalize:
                    self.assertEqual(v.encode(b'webp'), v.encode(b'webp'))
                    self.assertEqual(normalize.call_count, 1 if enabled else 2)
                    self.assertEqual(v.proc.stdin.getvalue().count('ENC '), 1)

    def test_changed_file_content_is_reloaded_and_not_served_by_path(self):
        with tempfile.TemporaryDirectory() as directory:
            v = self.make(directory)
            file = Path(directory)/'input.bin'
            with patch.object(Vision,'normalize',side_effect=lambda data:data):
                file.write_bytes(b'first'); first=v.encode(str(file))
                file.write_bytes(b'second'); second=v.encode(str(file))
            self.assertNotEqual(first, second)

    def test_evicted_embedding_is_not_returned_by_stale_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            v=self.make(directory)
            with patch.object(Vision,'normalize',side_effect=lambda data:data) as normalize:
                first=v.encode(b'one');v.cache.clear();second=v.encode(b'one')
                self.assertEqual(normalize.call_count,2)
                self.assertEqual(first,second)
                self.assertEqual(v.proc.stdin.getvalue().count('ENC '),2)

    def test_aliases_are_bounded_and_failed_encodes_are_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            v=self.make(directory)
            with patch.object(Vision,'normalize',side_effect=lambda data:data):
                for i in range(70):v.encode(str(i).encode())
                self.assertEqual(len(v.source_cache),64)
                v._readline=lambda *args:'ERR invalid'
                with self.assertRaises(ValueError):v.encode(b'bad')
                self.assertNotIn(hashlib.sha256(b'bad').hexdigest(),v.source_cache)


if __name__=='__main__':unittest.main()

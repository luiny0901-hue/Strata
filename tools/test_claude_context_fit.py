"""Keep the opt-in ON/OFF launch profiles usable with near-full Claude prompts."""
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from tools.strata_iq4xs_profiles import render_profile
from tools.claude_code_support import context_limits

ROOT = Path(__file__).resolve().parents[1]


class ClaudeContextFitTests(unittest.TestCase):
    def test_setup_hook_and_maintenance_entrypoints_load_outside_package_mode(self):
        for relative in ('tools/claude_opencodex_client.py', 'tools/claude_maintenance.py'):
            with self.subTest(entrypoint=relative):
                result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/relative), '--help'],
                                        cwd=ROOT, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_compaction_window_uses_the_model_window_without_a_second_output_reserve(self):
        for context, expected in ((262144, (32000, 262144)),
                                  (131072, (32000, 131072)),
                                  (100000, (25000, 100000)),
                                  (65536, (16384, 'auto'))):
            with self.subTest(context=context):
                self.assertEqual(context_limits(context), expected)

    def test_both_source_profiles_opt_in_without_lowering_context_or_gpu_reserve(self):
        for mode in ('on', 'off'):
            with self.subTest(mode=mode):
                path = ROOT/'profiles'/f'strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-{mode}.json.template'
                profile = json.loads(path.read_text(encoding='utf-8'))
                self.assertIs(profile.get('fit_max_tokens'), True)
                self.assertIs(profile.get('anthropic_tool_cache'), True)
                self.assertEqual(profile.get('effort_position'), 'end')
                args = profile['args']
                self.assertEqual(args[args.index('--max-context')+1], '262144')
                self.assertEqual(args[args.index('--vram-reserve-mib')+1], '448')

    def test_rendered_profiles_keep_the_output_headroom_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mode in ('on', 'off'):
                destination = root/(mode+'.json')
                render_profile(ROOT, mode, root/'Strata', root/'Data', destination)
                profile=json.loads(destination.read_text(encoding='utf-8'))
                self.assertIs(profile['fit_max_tokens'], True)
                self.assertIs(profile.get('anthropic_tool_cache'), True)
                self.assertEqual(profile['effort_position'], 'end')


if __name__ == '__main__':
    unittest.main()

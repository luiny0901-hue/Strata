"""CPU-only tests for the OpenCode long-session recovery installer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.configure_opencode_session_recovery import (  # noqa: E402
    DEFAULT_SOURCE,
    FULL_ACCESS_PERMISSION,
    UAC_DENY_POLICIES,
    apply_config,
    compaction_policy,
    configured_model_context,
)


SOURCE = DEFAULT_SOURCE


class InstallerTests(unittest.TestCase):
    def test_applies_recovery_values_and_preserves_existing_provider_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "opencode.json"
            config_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://opencode.ai/config.json",
                        "model": "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs",
                        "providers": {
                            "strata": {
                                "apiKey": "test-secret-preserved",
                                "models": {
                                    "qwen3.8-flash-next-unsloth-ud-iq4_xs": {
                                        "limit": {"context": 262144, "output": 32000}
                                    }
                                },
                            }
                        },
                        "instructions": ["~/custom/EXISTING.md"],
                        "agents": {"build": {"steps": 100}},
                        "compaction": {"auto": False, "keep": {"tokens": 20000}, "buffer": 32768},
                    }
                ),
                encoding="utf-8",
            )
            result = apply_config(config_path, SOURCE)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(config["compaction"]["auto"])
            self.assertEqual(config["compaction"]["keep"]["tokens"], 12000)
            self.assertEqual(config["compaction"]["buffer"], 65536)
            self.assertEqual(config["agents"]["build"]["steps"], 100)
            self.assertEqual(config["policies"], list(UAC_DENY_POLICIES))
            self.assertEqual(config["permissions"], [FULL_ACCESS_PERMISSION])
            self.assertEqual(config["model"], "strata/qwen3.8-flash-next-unsloth-ud-iq4_xs")
            self.assertEqual(config["providers"]["strata"]["apiKey"], "test-secret-preserved")
            self.assertEqual(
                config["providers"]["strata"]["models"]["qwen3.8-flash-next-unsloth-ud-iq4_xs"]["limit"],
                {"context": 262144, "output": 32000},
            )
            self.assertIn("~/custom/EXISTING.md", config["instructions"])
            self.assertEqual(len(config["instructions"]), 2)
            self.assertEqual(
                Path(result["instructions_path"]).read_text(encoding="utf-8"),
                SOURCE.read_text(encoding="utf-8").rstrip() + "\n",
            )
            self.assertTrue(result["config_backup"])
            self.assertTrue(Path(result["config_backup"]).is_file())

    def test_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            first = apply_config(config_path, SOURCE)
            first_bytes = config_path.read_bytes()
            second = apply_config(config_path, SOURCE)

            self.assertTrue(first["config_changed"])
            self.assertFalse(second["config_changed"])
            self.assertFalse(second["instructions_changed"])
            self.assertEqual(config_path.read_bytes(), first_bytes)
            config = json.loads(first_bytes)
            self.assertEqual(len(config["instructions"]), 1)
            self.assertTrue(config["instructions"][0].endswith("/STRATA_SESSION_RECOVERY_KO.md"))
            self.assertEqual(config["policies"], list(UAC_DENY_POLICIES))
            self.assertEqual(config["permissions"], [FULL_ACCESS_PERMISSION])

    def test_selected_small_model_scales_compaction_without_changing_its_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            config_path.write_text(
                json.dumps(
                    {
                        "model": "fixture/small",
                        "providers": {"fixture": {"models": {"small": {"limit": {"context": 8192}}}}},
                    }
                ),
                encoding="utf-8",
            )
            result = apply_config(config_path, SOURCE)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(result["context"], 8_192)
            self.assertEqual(config["compaction"], {"auto": True, "keep": {"tokens": 1_024}, "buffer": 2_048})
            self.assertEqual(configured_model_context(config), 8_192)

    def test_context_policy_rejects_invalid_values_and_unknown_models_use_safe_default(self):
        with self.assertRaisesRegex(ValueError, "at least 4096"):
            compaction_policy(2_048)
        self.assertEqual(configured_model_context({"model": "missing/model"}), 262_144)

    def test_existing_policies_are_preserved_and_uac_denies_are_last(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            custom = {"action": "tool.use", "resource": "shell:git status *", "effect": "allow"}
            config_path.write_text(json.dumps({"policies": [custom]}), encoding="utf-8")

            apply_config(config_path, SOURCE)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["policies"], [custom, *UAC_DENY_POLICIES])

    def test_full_access_rule_is_last_so_it_overrides_existing_ask_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            ask = {"action": "shell", "resource": "git push *", "effect": "ask"}
            config_path.write_text(json.dumps({"permissions": [ask]}), encoding="utf-8")

            apply_config(config_path, SOURCE)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["permissions"], [ask, FULL_ACCESS_PERMISSION])

    def test_malformed_policies_are_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = json.dumps({"policies": {"not": "a list"}}).encode("utf-8")
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "policies must be an array"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)

    def test_installed_recovery_instructions_define_uac_and_completion_boundaries(self):
        # Policy owners are split across registered files instead of duplicated.
        recovery = SOURCE.read_text(encoding="utf-8")
        basic = (SOURCE.parent / "KOREAN_INSTRUCTIONS.md").read_text(encoding="utf-8")
        for term in (
            "BLOCKED_UAC", "WAITING_FOR_USER_CONFIRMATION", "승인 완료, 계속",
            "완료는 종료 상태", "같은 기능의 두 번째 구현", "같은 수정을 두 작업자에게 동시에 맡기지 않는다",
            "이름이나 코드 유사성만으로 합치거나 삭제하지 않는다", "새 요구와 미완료 부분만 처리",
            "채팅 기록이 없는 새 세션", "인계 문서는 참고 근거이고 현재 실행 허가가 아니다",
            "과거 채팅을 요구하지 않는다", "매 단계마다 모든 서버의 목록과 사용법을 다시 조회하지 않는다",
            "전송 성공은 동작 성공이 아니다", "실제 상태 확인 없이 재전송하지 않는다",
            "관련 소스·설정·의존성·환경이 같을 때만 재사용",
        ):
            self.assertIn(term, recovery)
        for term in (
            "<!-- strata-intent-policy:v2 -->", "문장 전체의 부정·조건·인용",
            "설명만 원하나요, 실제 확인·수정까지 진행할까요?",
            "설계 문서만 수정할까요, 코드 구현·리팩터링까지 진행할까요?",
            "`설계 전용`, `문서 전용`, `구현` 중 하나",
            "설계안, TODO, 인수 기준, 예시 코드는 구현 권한이 아니며",
            "이미 허가된 미완료 작업은 범위를 유지하며 이어가되", "중지·보류·취소 요청이면 멈춘다",
            "placeholder·mock·미연결 UI·하드코딩 시연을 완성 구현으로 대신하지 않는다",
        ):
            self.assertIn(term, basic)

    def test_malformed_config_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = b'{"broken":'
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "unreadable JSON"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)
            self.assertFalse((Path(temp) / "STRATA_SESSION_RECOVERY_KO.md").exists())

    def test_invalid_instructions_value_is_refused_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "opencode.json"
            original = json.dumps({"instructions": [3]}).encode("utf-8")
            config_path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "array of strings"):
                apply_config(config_path, SOURCE)

            self.assertEqual(config_path.read_bytes(), original)
            self.assertFalse((Path(temp) / "STRATA_SESSION_RECOVERY_KO.md").exists())

    def test_existing_instruction_file_is_backed_up_before_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "opencode.json"
            target = root / "STRATA_SESSION_RECOVERY_KO.md"
            target.write_text("user-owned file\n", encoding="utf-8")

            result = apply_config(config_path, SOURCE)

            self.assertTrue(result["instructions_backup"])
            self.assertEqual(Path(result["instructions_backup"]).read_text(encoding="utf-8"), "user-owned file\n")
            self.assertEqual(target.read_text(encoding="utf-8"), SOURCE.read_text(encoding="utf-8").rstrip() + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)

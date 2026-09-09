from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import app_metadata
import batteryvault
import build


class VersionInfo(tuple):
    @property
    def major(self):
        return self[0]

    @property
    def minor(self):
        return self[1]


class ReleaseReliabilityTests(unittest.TestCase):
    def test_version_file_is_authoritative(self):
        version = Path("VERSION").read_text(encoding="utf-8").strip()

        self.assertEqual(version, "1.0.0")
        self.assertEqual(app_metadata.APP_VERSION, version)
        self.assertEqual(batteryvault.APP_VERSION, version)
        self.assertEqual(build.APP_VERSION, version)
        self.assertEqual(build.ZIP_PATH.name, f"BatteryVault_v{version}_Portable.zip")

    def test_runtime_requirements_do_not_include_pyinstaller(self):
        runtime = Path("requirements.txt").read_text(encoding="utf-8").lower()
        build_requirements = Path("requirements-build.txt").read_text(encoding="utf-8").lower()

        self.assertNotIn("pyinstaller", runtime)
        self.assertIn("pyinstaller", build_requirements)

    def test_spec_is_repo_relative_and_has_no_bytecode_fallback(self):
        spec = Path("BatteryVault.spec").read_text(encoding="utf-8")
        lower = spec.lower()

        self.assertIn("root = path(specpath)", lower)
        self.assertIn("icon=str(root / 'icon.ico')", lower)
        self.assertIn("(str(root / 'version'), '.')", lower)
        self.assertNotIn("c:\\users\\josh", lower)
        self.assertNotIn("_missing_stdlib_pycs", lower)
        self.assertNotIn("stdlib_pyc", lower)
        self.assertNotIn("encodings_pyc", lower)
        self.assertNotIn("rthook_fix_encodings", lower)
        self.assertIn("win32com.client", lower)
        self.assertIn("pythoncom", lower)
        self.assertIn("wmi", lower)

    def test_build_script_filters_environment_specific_path_entries(self):
        python_root = Path(r"C:\Users\Josh\AppData\Local\Programs\Python\Python311")

        self.assertFalse(
            build._is_path_entry_allowed(
                r"C:\Users\Josh\.cache\codex-runtimes\poppler\Library\bin",
                python_root,
            )
        )
        self.assertFalse(
            build._is_path_entry_allowed(
                r"C:\Users\Josh\AppData\Local\Programs\libheif\bin",
                python_root,
            )
        )
        self.assertFalse(
            build._is_path_entry_allowed(
                "C:/Users/Josh/.cache/codex-runtimes/poppler/Library/bin",
                python_root,
            )
        )
        self.assertTrue(build._is_path_entry_allowed(str(python_root), python_root))
        self.assertTrue(build._is_path_entry_allowed(str(python_root / "Scripts"), python_root))

    def test_build_script_refuses_to_clean_repo_root(self):
        with self.assertRaisesRegex(RuntimeError, "repository root"):
            build._assert_within_repo(build.ROOT)

    def test_build_script_requires_python_311(self):
        with mock.patch.object(build.sys, "version_info", VersionInfo((3, 10, 12))):
            with self.assertRaisesRegex(RuntimeError, "requires Python 3.11"):
                build.assert_python_311()

    def test_bundle_audit_rejects_unexpected_root_dll_and_dev_files(self):
        with tempfile.TemporaryDirectory() as td:
            app_dir = Path(td) / "BatteryVault"
            internal = app_dir / "_internal"
            internal.mkdir(parents=True)
            (app_dir / "BatteryVault.exe").write_bytes(b"exe")
            (app_dir / "README.txt").write_text("readme", encoding="utf-8")
            (app_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
            (app_dir / "Qt6Core.dll").write_bytes(b"dll")

            with mock.patch.object(build, "APP_DIR", app_dir), mock.patch.object(
                build, "EXE_PATH", app_dir / "BatteryVault.exe"
            ):
                with self.assertRaisesRegex(RuntimeError, "root-level DLL"):
                    build.validate_bundle()

            (app_dir / "Qt6Core.dll").unlink()
            (internal / "bad.pyc").write_bytes(b"pyc")
            with mock.patch.object(build, "APP_DIR", app_dir), mock.patch.object(
                build, "EXE_PATH", app_dir / "BatteryVault.exe"
            ):
                with self.assertRaisesRegex(RuntimeError, "stale files"):
                    build.validate_bundle()

    def test_bundle_audit_accepts_normal_onedir_shape(self):
        with tempfile.TemporaryDirectory() as td:
            app_dir = Path(td) / "BatteryVault"
            internal = app_dir / "_internal"
            internal.mkdir(parents=True)
            (app_dir / "BatteryVault.exe").write_bytes(b"exe")
            (app_dir / "README.txt").write_text("readme", encoding="utf-8")
            (app_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
            (internal / "python311.dll").write_bytes(b"dll")

            with mock.patch.object(build, "APP_DIR", app_dir), mock.patch.object(
                build, "EXE_PATH", app_dir / "BatteryVault.exe"
            ):
                build.validate_bundle()

    def test_portable_zip_contains_app_folder(self):
        with tempfile.TemporaryDirectory() as td:
            app_dir = Path(td) / "BatteryVault"
            zip_path = Path(td) / "BatteryVault_v1.0.0_Portable.zip"
            internal = app_dir / "_internal"
            internal.mkdir(parents=True)
            (app_dir / "BatteryVault.exe").write_bytes(b"exe")
            (internal / "dependency.dll").write_bytes(b"dll")

            with mock.patch.object(build, "APP_DIR", app_dir), mock.patch.object(
                build, "ZIP_PATH", zip_path
            ):
                build.create_portable_zip()

            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
            self.assertIn("BatteryVault/BatteryVault.exe", names)
            self.assertIn("BatteryVault/_internal/dependency.dll", names)

    def test_no_battery_and_telemetry_failures_degrade_without_hardware(self):
        reader = batteryvault.BatteryReader()
        with mock.patch.object(batteryvault.psutil, "sensors_battery", return_value=None), mock.patch.object(
            reader, "_ensure_wmi", return_value=None
        ):
            data = reader.read()

        self.assertFalse(data.has_battery)
        self.assertEqual(data.status, "No battery")

        reader = batteryvault.BatteryReader()
        with mock.patch.object(
            batteryvault.psutil, "sensors_battery", side_effect=RuntimeError("blocked")
        ), mock.patch.object(reader, "_ensure_wmi", return_value=None):
            data = reader.read()

        self.assertFalse(data.has_battery)
        self.assertEqual(data.status, "No battery")

    def test_packaged_smoke_exit_is_environment_only(self):
        source = Path("batteryvault.py").read_text(encoding="utf-8")

        self.assertIn("BATTERYVAULT_SMOKE_EXIT_MS", source)
        self.assertIn("QTimer.singleShot", source)

    def test_github_actions_build_verifies_package_without_releasing(self):
        workflow = Path(".github/workflows/build-verification.yml").read_text(encoding="utf-8")

        self.assertIn("python-version: '3.11'", workflow)
        self.assertIn("python -B -m unittest discover -s tests -v", workflow)
        self.assertIn("python -B -m py_compile batteryvault.py app_metadata.py build.py", workflow)
        self.assertIn("python -B build.py", workflow)
        self.assertIn("dist\\BatteryVault\\BatteryVault.exe", workflow)
        self.assertIn("dist\\BatteryVault_v$(Get-Content VERSION)_Portable.zip", workflow)
        self.assertIn("actions/upload-artifact", workflow)
        self.assertNotIn("softprops/action-gh-release", workflow)
        self.assertNotIn("git tag", workflow.lower())


if __name__ == "__main__":
    unittest.main()

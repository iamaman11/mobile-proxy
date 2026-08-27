import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "scripts" / "mobile-proxy-ip"


class MobileProxyIpWrapperTests(unittest.TestCase):
    @staticmethod
    def write_fake_operator(directory: str) -> Path:
        fake_operator = Path(directory) / "operator-cli"
        fake_operator.write_text(
            r"""#!/bin/sh
set -eu
[ "$1" = "ip" ]
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy; do
  eval "value=\${$name-}"
  [ -z "$value" ] || exit 91
done
printf '%s\n' '{"success":true}'
""",
            encoding="utf-8",
        )
        fake_operator.chmod(fake_operator.stat().st_mode | stat.S_IXUSR)
        return fake_operator

    def test_control_process_never_inherits_proxy_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_operator = self.write_fake_operator(directory)
            environment = os.environ.copy()
            environment.update(
                {
                    "MOBILE_PROXY_CLIENT_ENV": str(Path(directory) / "missing.env"),
                    "MOBILE_PROXY_OPERATOR_CLI": str(fake_operator),
                    "MOBILE_PROXY_ROTATION_TOKEN": "test-rotation-token",
                    "MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64": "test-certificate",
                    "HTTP_PROXY": "http://127.0.0.1:1",
                    "HTTPS_PROXY": "http://127.0.0.1:1",
                    "ALL_PROXY": "socks5h://127.0.0.1:1",
                    "NO_PROXY": "localhost",
                    "http_proxy": "http://127.0.0.1:1",
                    "https_proxy": "http://127.0.0.1:1",
                    "all_proxy": "socks5h://127.0.0.1:1",
                    "no_proxy": "localhost",
                }
            )
            completed = subprocess.run(
                [str(WRAPPER), "--format", "json"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), '{"success":true}')

    def test_vault_paths_do_not_depend_on_callers_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_operator = self.write_fake_operator(directory)
            fake_vault = Path(directory) / "secret-vault"
            fake_vault.write_text(
                r"""#!/bin/sh
set -eu
[ "$SECRET_VAULT_ROOT" = /home/bose/projects/secret-vault ]
[ "$SECRET_VAULT_GNUPGHOME" = /home/bose/.local/share/codex-secret-vault/gnupg ]
[ "$1" = run ]
name="$2"
env_name="$3"
shift 4
case "$name" in
  mobile-proxy.rotation-token) value=test-rotation-token ;;
  mobile-proxy.reverse-tunnel-cert-der-b64) value=test-certificate ;;
  *) exit 92 ;;
esac
export "$env_name=$value"
exec "$@"
""",
                encoding="utf-8",
            )
            fake_vault.chmod(fake_vault.stat().st_mode | stat.S_IXUSR)
            environment = os.environ.copy()
            environment.pop("MOBILE_PROXY_ROTATION_TOKEN", None)
            environment.pop("MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64", None)
            environment.update(
                {
                    "HOME": str(Path(directory) / "isolated-home"),
                    "MOBILE_PROXY_CLIENT_ENV": str(Path(directory) / "missing.env"),
                    "MOBILE_PROXY_OPERATOR_CLI": str(fake_operator),
                    "MOBILE_PROXY_SECRET_VAULT": str(fake_vault),
                }
            )

            completed = subprocess.run(
                [str(WRAPPER), "--format", "json"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), '{"success":true}')

    def test_default_client_config_is_independent_of_callers_home(self) -> None:
        wrapper = WRAPPER.read_text(encoding="utf-8")

        self.assertIn(
            '${XDG_CONFIG_HOME:-/home/bose/.config}/mobile-proxy/client.env',
            wrapper,
        )


if __name__ == "__main__":
    unittest.main()

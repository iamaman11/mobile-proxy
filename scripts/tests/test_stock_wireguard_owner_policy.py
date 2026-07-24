import pathlib
import unittest


ANDROID_SOURCE = (
    pathlib.Path(__file__).parents[2]
    / "services"
    / "runtime-supervisor"
    / "src"
    / "android.rs"
)


class StockWireguardOwnerPolicyTests(unittest.TestCase):
    def test_stock_kick_never_starts_first_party_vpn(self):
        source = ANDROID_SOURCE.read_text(encoding="utf-8")
        start = source.index("pub async fn kick_stock_wireguard_bridge()")
        end = source.index("pub fn ensure_cellular_default_route()", start)
        body = source[start:end]
        self.assertIn("com.wireguard.android", body)
        self.assertIn("WiGandroid", body)
        self.assertNotIn("com.example.mobileproxy", body)
        self.assertNotIn("kick_first_party_vpn_service", body)


if __name__ == "__main__":
    unittest.main()

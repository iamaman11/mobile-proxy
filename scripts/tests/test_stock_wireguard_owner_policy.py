import pathlib
import unittest


ANDROID_SOURCE = (
    pathlib.Path(__file__).parents[2]
    / "services"
    / "runtime-supervisor"
    / "src"
    / "android.rs"
)
SUPERVISOR_MAIN = (
    pathlib.Path(__file__).parents[2]
    / "services"
    / "runtime-supervisor"
    / "src"
    / "main.rs"
)


class StockWireguardOwnerPolicyTests(unittest.TestCase):
    def test_stock_kick_never_starts_first_party_vpn(self):
        source = ANDROID_SOURCE.read_text(encoding="utf-8")
        start = source.index("pub async fn kick_stock_wireguard_bridge()")
        end = source.index("pub fn stop_compatibility_vpns()", start)
        body = source[start:end]
        self.assertIn("com.wireguard.android", body)
        self.assertIn("WiGandroid", body)
        self.assertNotIn("com.example.mobileproxy", body)
        self.assertNotIn("kick_first_party_vpn_service", body)

    def test_reverse_startup_stops_both_compatibility_vpns(self):
        source = ANDROID_SOURCE.read_text(encoding="utf-8")
        start = source.index("pub fn stop_compatibility_vpns()")
        end = source.index("pub fn ensure_cellular_default_route()", start)
        body = source[start:end]
        self.assertIn("com.example.mobileproxy.action.STOP_TUNNEL", body)
        self.assertIn("com.wireguard.android.action.SET_TUNNEL_DOWN", body)
        self.assertIn("settings delete secure always_on_vpn_app", body)

        main = SUPERVISOR_MAIN.read_text(encoding="utf-8")
        self.assertIn("TunnelOwner::FirstPartyReverseTunnel", main)
        self.assertIn("stop_compatibility_vpns()", main)


if __name__ == "__main__":
    unittest.main()

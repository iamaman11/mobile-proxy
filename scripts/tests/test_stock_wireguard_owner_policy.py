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
SUPERVISOR_CONFIG = (
    pathlib.Path(__file__).parents[2]
    / "services"
    / "runtime-supervisor"
    / "src"
    / "config.rs"
)


class StockWireguardOwnerPolicyTests(unittest.TestCase):
    def test_stock_kick_and_first_party_kick_are_separate_paths(self):
        source = ANDROID_SOURCE.read_text(encoding="utf-8")
        start = source.index("pub async fn kick_stock_wireguard_bridge()")
        end = source.index("pub async fn kick_first_party_vpn_service", start)
        body = source[start:end]
        self.assertIn("com.wireguard.android", body)
        self.assertIn("stop_stock_wireguard_tunnel", body)
        self.assertIn("start_stock_wireguard_tunnel", body)

        first_party_start = source.index("pub async fn kick_first_party_vpn_service", 0)
        first_party_end = source.index("pub fn stop_compatibility_vpns()", first_party_start)
        first_party_body = source[first_party_start:first_party_end]
        self.assertIn("com.example.mobileproxy", first_party_body)
        self.assertIn("START_TUNNEL", first_party_body)

    def test_non_stock_startup_stops_compatibility_vpns(self):
        source = ANDROID_SOURCE.read_text(encoding="utf-8")
        start = source.index("pub fn stop_compatibility_vpns()")
        end = source.index("pub fn ensure_cellular_default_route()", start)
        body = source[start:end]
        self.assertIn("stop_stock_wireguard_tunnel", body)
        self.assertIn("stop_first_party_vpn_service", body)
        self.assertIn("settings delete secure always_on_vpn_app", body)

        main = SUPERVISOR_MAIN.read_text(encoding="utf-8")
        self.assertIn("TunnelOwner::StockWireguardBridge", main)
        self.assertIn("stop_compatibility_vpns()", main)

    def test_runtime_owner_contract_includes_android_vpn_service(self):
        config = SUPERVISOR_CONFIG.read_text(encoding="utf-8")
        enum_start = config.index("pub enum TunnelOwner")
        enum_end = config.index("impl TunnelOwner", enum_start)
        owner_enum = config[enum_start:enum_end]
        self.assertIn("FirstPartyReverseTunnel", owner_enum)
        self.assertIn("StockWireguardBridge", owner_enum)
        self.assertIn("FirstPartyVpnService", owner_enum)
        self.assertIn('TunnelOwner::parse("first_party_vpn_service").unwrap()', config)


if __name__ == "__main__":
    unittest.main()

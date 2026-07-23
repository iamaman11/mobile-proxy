from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    target = Path(path)
    body = target.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(body.replace(old, new, 1))


model_path = Path("crates/reverse-tunnel/src/model.rs")
model = model_path.read_text()

same_transport = "            (Some(current), next) if current as u8 == next as u8 => None,\n"
if model.count(same_transport) != 1:
    raise RuntimeError("expected exactly one same-transport match arm")
model = model.replace(same_transport, "            _ => None,\n", 1)

derive_old = (
    "#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]\n"
    "#[serde(deny_unknown_fields)]\n"
    "pub struct TunnelEventCounters {\n"
)
derive_new = (
    "#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]\n"
    "#[serde(deny_unknown_fields)]\n"
    "pub struct TunnelEventCounters {\n"
)
if model.count(derive_old) != 1:
    raise RuntimeError("expected one TunnelEventCounters derive")
model = model.replace(derive_old, derive_new, 1)

default_start = model.find("impl Default for TunnelEventCounters {")
default_end = model.find("\n\nimpl TunnelEventCounters {", default_start)
if default_start < 0 or default_end < 0:
    raise RuntimeError("failed to locate manual TunnelEventCounters Default")
model = model[:default_start] + model[default_end + 2 :]

durable_anchor = "    pub const fn reconnect_attempts(&self) -> u64 {\n"
if model.count(durable_anchor) != 1:
    raise RuntimeError("expected one reconnect attempts anchor")
durable_method = (
    "    pub fn same_persisted_state(&self, other: &Self) -> bool {\n"
    "        self.connection_counts == other.connection_counts\n"
    "            && self.transition_counts == other.transition_counts\n"
    "            && self.failover_counts == other.failover_counts\n"
    "            && self.disconnect_counts == other.disconnect_counts\n"
    "            && self.reconnect_attempts == other.reconnect_attempts\n"
    "            && self.reconnect_successes == other.reconnect_successes\n"
    "            && self.ever_connected == other.ever_connected\n"
    "            && self.last_successful_transport == other.last_successful_transport\n"
    "    }\n\n"
)
model = model.replace(durable_anchor, durable_method + durable_anchor, 1)

constructor_old = (
    "impl ClientSnapshot {\n"
    "    pub(crate) fn new(session_id: Uuid) -> Self {\n"
)
constructor_new = (
    "impl ClientSnapshot {\n"
    "    #[cfg(test)]\n"
    "    pub(crate) fn new(session_id: Uuid) -> Self {\n"
)
if model.count(constructor_old) != 1:
    raise RuntimeError("expected one ClientSnapshot test constructor")
model_path.write_text(model.replace(constructor_old, constructor_new, 1))

replace_exact(
    "services/host-daemon/src/reverse_tunnel.rs",
    "    ClientSnapshot, ReverseTunnelClientConfig, TunnelEventCounters, TunnelFreshness,\n",
    "    ClientSnapshot, ReverseTunnelClientConfig, TunnelFreshness,\n",
)

store_path = Path("services/host-daemon/src/tunnel_counters.rs")
store = store_path.read_text()
old = "        if self.current == *counters {\n"
new = "        if self.current.same_persisted_state(counters) {\n"
if store.count(old) != 1:
    raise RuntimeError("expected one persistence equality check")
store = store.replace(old, new, 1)
old = "        assert_eq!(reloaded.counters(), &counters);\n"
new = "        assert!(reloaded.counters().same_persisted_state(&counters));\n"
if store.count(old) != 1:
    raise RuntimeError("expected one round-trip equality assertion")
store_path.write_text(store.replace(old, new, 1))

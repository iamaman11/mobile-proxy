use anyhow::{Result, bail};
use proxy_core::{DesiredVm, LifecycleScope, OwnershipIntent};

use crate::vultr_lifecycle::VultrVmSpec;

const ACCEPTANCE_REGION: &str = "waw";
const ACCEPTANCE_PLAN: &str = "vc2-1c-2gb";
const ACCEPTANCE_OS_ID: u64 = 2284;
const ACCEPTANCE_LABEL: &str = "mobile-proxy-acceptance";
const ITEM20_INTENT_PREFIX: &str = "item20:candidate:";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Item20SessionIdentity {
    candidate_sha: String,
    control_plane_sha: String,
}

impl Item20SessionIdentity {
    pub fn new(
        candidate_sha: impl Into<String>,
        control_plane_sha: impl Into<String>,
    ) -> Result<Self> {
        let candidate_sha = candidate_sha.into();
        let control_plane_sha = control_plane_sha.into();
        validate_full_sha(&candidate_sha, "candidate")?;
        validate_full_sha(&control_plane_sha, "control-plane")?;
        if candidate_sha != control_plane_sha {
            bail!(
                "candidate/control-plane SHA mismatch violates 10/10 single-SHA Item 20 identity"
            );
        }
        Ok(Self {
            candidate_sha,
            control_plane_sha,
        })
    }

    pub fn candidate_sha(&self) -> &str {
        &self.candidate_sha
    }

    pub fn control_plane_sha(&self) -> &str {
        &self.control_plane_sha
    }

    pub fn ownership_intent(&self) -> Result<OwnershipIntent> {
        Ok(OwnershipIntent::new(
            LifecycleScope::Acceptance,
            format!("{ITEM20_INTENT_PREFIX}{}", self.candidate_sha),
        )?)
    }

    pub fn desired_vm(&self) -> Result<DesiredVm> {
        let spec = acceptance_spec();
        Ok(DesiredVm {
            intent: self.ownership_intent()?,
            display_name: spec.label.clone(),
            spec_fingerprint: spec.fingerprint(),
        })
    }
}

pub fn acceptance_spec() -> VultrVmSpec {
    VultrVmSpec {
        region: ACCEPTANCE_REGION.to_owned(),
        plan: ACCEPTANCE_PLAN.to_owned(),
        os_id: ACCEPTANCE_OS_ID,
        label: ACCEPTANCE_LABEL.to_owned(),
    }
}

fn validate_full_sha(value: &str, kind: &str) -> Result<()> {
    if value.len() != 40
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        bail!("{kind} SHA must be an exact lowercase 40-character hexadecimal commit identity");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const ACCEPTED_SHA: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const OTHER_SHA: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    #[test]
    fn item20_intent_is_acceptance_only_and_distinct_from_item19_terminal_intent() {
        let identity = Item20SessionIdentity::new(ACCEPTED_SHA, ACCEPTED_SHA).unwrap();
        let intent = identity.ownership_intent().unwrap();
        assert_eq!(intent.scope(), LifecycleScope::Acceptance);
        assert_eq!(
            intent.id(),
            "item20:candidate:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        );
        assert_ne!(intent.id(), format!("candidate:{ACCEPTED_SHA}"));
    }

    #[test]
    fn candidate_and_control_plane_must_be_exactly_equal() {
        let identity = Item20SessionIdentity::new(ACCEPTED_SHA, ACCEPTED_SHA).unwrap();
        assert_eq!(identity.candidate_sha(), ACCEPTED_SHA);
        assert_eq!(identity.control_plane_sha(), ACCEPTED_SHA);
        assert!(Item20SessionIdentity::new(ACCEPTED_SHA, OTHER_SHA).is_err());
    }

    #[test]
    fn mutable_short_or_uppercase_refs_are_rejected() {
        for value in [
            "main",
            "aaaaaaa",
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaag",
        ] {
            assert!(Item20SessionIdentity::new(value, ACCEPTED_SHA).is_err());
            assert!(Item20SessionIdentity::new(ACCEPTED_SHA, value).is_err());
        }
    }

    #[test]
    fn desired_vm_uses_the_bounded_acceptance_spec() {
        let identity = Item20SessionIdentity::new(ACCEPTED_SHA, ACCEPTED_SHA).unwrap();
        let desired = identity.desired_vm().unwrap();
        let spec = acceptance_spec();
        assert_eq!(desired.intent, identity.ownership_intent().unwrap());
        assert_eq!(desired.display_name, spec.label);
        assert_eq!(desired.spec_fingerprint, spec.fingerprint());
    }
}

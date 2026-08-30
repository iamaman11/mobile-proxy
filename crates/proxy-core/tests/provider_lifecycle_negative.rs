use proxy_core::{
    DesiredVm, Generation, LifecycleError, LifecycleScope, ObservedVm, OwnershipIntent,
    OwnershipMetadata, OwnershipObservation, ProviderResourceId, plan_present,
};

#[test]
fn same_name_with_complete_wrong_owner_metadata_is_rejected() {
    let intent =
        OwnershipIntent::new(LifecycleScope::Acceptance, "candidate:0123456789abcdef").unwrap();
    let desired = DesiredVm {
        intent: intent.clone(),
        display_name: "mobile-proxy-acceptance".to_owned(),
        spec_fingerprint: "spec:v1".to_owned(),
    };
    let neighbour = ObservedVm {
        provider_id: ProviderResourceId::new("22222222-2222-4222-8222-222222222222").unwrap(),
        display_name: desired.display_name.clone(),
        ownership: OwnershipObservation::Exact(OwnershipMetadata {
            project: "other-project".to_owned(),
            managed_by: "other-manager".to_owned(),
            scope: intent.scope(),
            intent_id: intent.id().to_owned(),
            generation: Generation::INITIAL,
        }),
        spec_fingerprint: desired.spec_fingerprint.clone(),
    };

    assert_eq!(
        plan_present(None, &[neighbour], &desired, None),
        Err(LifecycleError::NeighboringOrUnboundResource)
    );
}

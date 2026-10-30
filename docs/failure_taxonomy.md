# Failure taxonomy and repair policy

The benchmark exercises four configured classes plus an unknown/unclassified path. This is a deliberately narrow taxonomy, not a claim that production pipeline incidents fall neatly into four groups.

| Coarse type | Root-cause subtypes / examples | Current policy |
|---|---|---|
| `schema_change` | One-to-one column rename; general schema/column-order mismatch | `rename_column` only after schema and value preservation checks |
| `data_quality` | Missing feature values; non-finite feature values; incompatible feature types; unclassified domain/sentinel errors | `impute_missing_values` only for the explicitly supported missing-feature subtype; unsupported subtypes should be escalated |
| `configuration_error` | Invalid named parameter; configuration failure without a parseable parameter | `restore_configuration` only for supported parameters and values, followed by training/evaluation checks |
| `dependency_error` | Missing Python module; binary/runtime import error | `verify_dependency` plus human review; do not automatically install/change packages |
| Unknown/unsupported | Permission failures, resource exhaustion, storage/network errors outside current handlers, ambiguous data checks | Preserve an unknown/unclassified diagnosis and request more evidence or human review |

The action allowlist enforces a match between coarse fault type and action. Validators separately inspect action-specific parameters and data/configuration invariants. Passing one layer does not prove a proposal is semantically correct; a reviewer and further tests remain necessary for a research prototype.

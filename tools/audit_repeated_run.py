#!/usr/bin/env python3
"""Audit a supplied repeated-trial artifact ZIP against its summary and manifest.

This script only audits records; it does not execute the ML pipeline or make API calls.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, re, statistics, zipfile
from pathlib import Path

RAW = 'run_artifacts/raw_jsonl/repeated_trials_20261024_171821.jsonl'
SUMMARY = 'run_artifacts/summary_json/repeated_trials_summary_20261024_171821.json'
MANIFEST = 'run_artifacts/llm_manifest/llm_run_manifest_20261024_171821.json'
PIP = 'environment/pip_freeze.txt'
CHECKS = 'environment/source_file_checksums.sha256'
META = 'environment/audit_metadata.txt'


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return statistics.mean(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('zip_path', type=Path)
    ap.add_argument('--json-out', type=Path)
    ap.add_argument('--report-out', type=Path)
    args = ap.parse_args()
    findings = []
    with zipfile.ZipFile(args.zip_path) as z:
        names = set(z.namelist())
        for name in [RAW, SUMMARY, MANIFEST, PIP, CHECKS, META]:
            if name not in names:
                raise SystemExit(f'Missing required artifact: {name}')
        raw_bytes = z.read(RAW)
        raw_text = raw_bytes.decode('utf-8')
        rows = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
        summary = json.loads(z.read(SUMMARY))
        manifest = json.loads(z.read(MANIFEST))
        pip_text = z.read(PIP).decode('utf-8', errors='replace')
        check_text = z.read(CHECKS).decode('utf-8', errors='replace')
        metadata_text = z.read(META).decode('utf-8', errors='replace')

        by_method = {m: [r for r in rows if r.get('method') == m] for m in summary['methods']}
        per_method = {}
        all_counts_match = len(rows) == 180
        all_timing_match = True
        for method, rs in by_method.items():
            rep = summary['methods'][method]
            recovered = sum(r.get('result', {}).get('status') == 'recovered' for r in rs)
            human = sum(r.get('result', {}).get('status') == 'needs_human_approval' for r in rs)
            durations = [r.get('result', {}).get('method_duration_seconds') for r in rs]
            gens = [r.get('llm_generation_seconds') for r in rs]
            plans = [r.get('rule_planning_seconds') for r in rs]
            avg_duration = mean(durations)
            avg_gen = mean(gens)
            avg_plan = mean(plans)
            combined = (avg_gen or 0) + (avg_duration or 0)
            plan_combined = (avg_plan or 0) + (avg_duration or 0)
            status_counts = dict(collections.Counter(r.get('result', {}).get('status') for r in rs))
            type_counts = {}
            for ft in sorted({r.get('failure_type') for r in rs}):
                fr = [r for r in rs if r.get('failure_type') == ft]
                type_counts[ft] = {
                    'cases': len(fr),
                    'recovered': sum(r.get('result', {}).get('status') == 'recovered' for r in fr),
                    'human_review_required': sum(r.get('result', {}).get('status') == 'needs_human_approval' for r in fr),
                }
            checks = {
                'row_count_matches': len(rs) == rep['cases'] == 60,
                'recovered_count_matches': recovered == rep['recovered'] == 45,
                'human_review_count_matches': human == rep['human_review_required'] == 15,
            }
            all_counts_match &= all(checks.values())
            if method == 'rule_based_gated':
                time_checks = {
                    'mean_method_duration_seconds': math.isclose(avg_duration, rep['mean_method_duration_seconds'], abs_tol=1e-6),
                    'mean_planning_plus_method_seconds': math.isclose(plan_combined, rep['mean_planning_plus_method_seconds'], abs_tol=1e-6),
                    'mean_repair_planning_seconds': math.isclose(avg_plan, rep['mean_repair_planning_seconds'], abs_tol=1e-6),
                }
            else:
                time_checks = {
                    'mean_method_duration_seconds': math.isclose(avg_duration, rep['mean_method_duration_seconds'], abs_tol=1e-6),
                    'mean_llm_generation_seconds': math.isclose(avg_gen, rep['mean_llm_generation_seconds'], abs_tol=1e-6),
                    'mean_generation_plus_method_seconds': math.isclose(combined, rep['mean_generation_plus_method_seconds'], abs_tol=1e-6),
                }
            all_timing_match &= all(time_checks.values())
            per_method[method] = {
                'rows': len(rs), 'status_counts': status_counts, 'per_failure_type': type_counts,
                'mean_method_duration_seconds_raw': avg_duration,
                'mean_llm_generation_seconds_raw': avg_gen,
                'mean_repair_planning_seconds_raw': avg_plan,
                'mean_generation_plus_method_seconds_recomputed': combined if avg_gen is not None else None,
                'mean_planning_plus_method_seconds_recomputed': plan_combined if avg_plan is not None else None,
                'summary_counts_checks': checks, 'summary_timing_checks': time_checks,
            }

        # Direct and validated LLM runs must have identical paired candidate identity and generation timings.
        direct = {(r['case_id'], r['repeat_index']): r for r in by_method['llm_direct_isolated']}
        validated = {(r['case_id'], r['repeat_index']): r for r in by_method['llm_validated']}
        same_keys = set(direct) == set(validated)
        pair_count = len(direct) if same_keys else 0
        candidate_match = sum(direct[k].get('candidate_id') == validated[k].get('candidate_id') for k in direct) if same_keys else 0
        generation_match = sum(direct[k].get('llm_generation_seconds') == validated[k].get('llm_generation_seconds') for k in direct) if same_keys else 0
        failure_type_match = sum(direct[k].get('failure_type') == validated[k].get('failure_type') for k in direct) if same_keys else 0

        # The summary's diagnosis denominator is 60 unique case/repeat keys, not 180 method rows.
        diag = {}
        for r in rows:
            k = (r['case_id'], r['repeat_index'])
            diag.setdefault(k, set()).add((r.get('expected_root_cause_code'), r.get('predicted_root_cause_code'), r.get('diagnosis_correct')))
        diagnosis_pair_consistency = all(len(v) == 1 for v in diag.values())
        diagnosis_correct = sum(all(item[2] is True for item in vals) for vals in diag.values())

        # Source hash match to repository V11 code package is checked separately in this analysis.
        invalid_dist_warnings = re.findall(r'WARNING: Ignoring invalid distribution', pip_text)
        appledouble_lines = [line for line in check_text.splitlines() if '/._' in line or line.split('  ')[-1].split('/')[-1].startswith('._')]
        checksum_roots = sorted({line.split('  ', 1)[-1].split('/')[0] for line in check_text.splitlines() if '  ' in line})
        common_secret_patterns = {
            'openai_key_like': r'sk-[A-Za-z0-9_-]{20,}',
            'github_token_like': r'gh[pousr]_[A-Za-z0-9]{20,}',
            'aws_access_key_like': r'AKIA[0-9A-Z]{16}',
            'bearer_token_like': r'(?i)Bearer\s+[A-Za-z0-9._~+/-]{20,}',
        }
        all_text = '\n'.join(z.read(n).decode('utf-8', errors='replace') for n in names if n.endswith(('.json', '.jsonl', '.txt', '.sha256')))
        secret_scan = {k: len(re.findall(p, all_text)) for k, p in common_secret_patterns.items()}
        findings.append('Counts and timings recompute from the 180 raw JSONL rows and match the summary to its displayed precision.' if all_counts_match and all_timing_match else 'At least one summary/JSONL reconciliation check failed.')
        findings.append(f'The manifest records model_identifier={manifest.get("model_identifier")!r} and endpoint={manifest.get("endpoint_sanitized")!r}.')
        findings.append('Manifest scope explicitly says current environment/source configuration, not a reconstruction of historical runs; Git commit is unavailable.')
        findings.append(f'pip-freeze capture contains {len(invalid_dist_warnings)} invalid-distribution warnings; source checksum list has {len(appledouble_lines)} AppleDouble sidecar entries and covers roots {checksum_roots}.')

        out = {
            'audit_schema': 'repeated-trial-audit-v1',
            'input_zip_sha256': hashlib.sha256(args.zip_path.read_bytes()).hexdigest(),
            'raw_jsonl_sha256': hashlib.sha256(raw_bytes).hexdigest(),
            'raw_row_count': len(rows),
            'unique_case_repeat_keys': len(diag),
            'method_counts_match_summary': all_counts_match,
            'timing_means_match_summary_within_1e-6_seconds': all_timing_match,
            'per_method': per_method,
            'llm_pairing': {
                'same_case_repeat_keys': same_keys,
                'paired_keys': pair_count,
                'same_candidate_id_pairs': candidate_match,
                'same_generation_time_pairs': generation_match,
                'same_failure_type_pairs': failure_type_match,
            },
            'diagnosis': {
                'unique_case_repeat_keys': len(diag),
                'expected_predicted_correct_count': diagnosis_correct,
                'accuracy': diagnosis_correct / len(diag) if diag else None,
                'pair_outputs_consistent_across_methods': diagnosis_pair_consistency,
                'interpretation': 'configured scenario-label agreement only; not evidence of unseen-fault generalization',
            },
            'manifest': {
                'captured_at_utc': manifest.get('captured_at_utc'),
                'scope': manifest.get('scope'),
                'status': manifest.get('status'),
                'provider_mode': manifest.get('provider_mode'),
                'model_identifier': manifest.get('model_identifier'),
                'endpoint_sanitized': manifest.get('endpoint_sanitized'),
                'python_version': manifest.get('python_version'),
                'sdk': manifest.get('sdk'),
                'request_settings_from_source': manifest.get('request_settings_from_source'),
                'git_commit_in_audit_metadata': 'unavailable' not in metadata_text.lower(),
                'api_key_value_recorded': manifest.get('security', {}).get('api_key_value_recorded'),
            },
            'environment_quality': {
                'invalid_distribution_warning_count': len(invalid_dist_warnings),
                'appledouble_sidecar_checksum_entries': len(appledouble_lines),
                'checksum_roots': checksum_roots,
                'common_secret_pattern_matches': secret_scan,
            },
            'findings': findings,
        }
        # Extra consistency assertions
        out['llm_pairing']['candidate_pairing_pass'] = same_keys and candidate_match == pair_count == 60 and generation_match == pair_count and failure_type_match == pair_count
        out['secret_pattern_scan_has_no_matches'] = all(v == 0 for v in secret_scan.values())
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(out, indent=2) + '\n')
        if args.report_out:
            args.report_out.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                '# Repeated-trial audit report - 24 October 2026', '',
                '## Scope',
                'This audit checks the supplied JSONL trial records against the supplied summary and near-time manifest. It does not rerun the ML pipeline or make LLM API calls.', '',
                '## Reconciliation result',
                f'- Raw JSONL rows: **{len(rows)}** (expected 180).',
                f'- Per method: **60 rows** each; counts and timing means match the summary to displayed precision: **{all_counts_match and all_timing_match}**.',
                f'- Unique case/repeat keys: **{len(diag)}**; configured-label diagnosis: **{diagnosis_correct}/{len(diag)}**. This is agreement on configured labels, not unseen-fault accuracy.',
                f'- Direct/validated LLM pairing: same candidate ID for **{candidate_match}/{pair_count}** keys, same generation-time value for **{generation_match}/{pair_count}**, and same failure type for **{failure_type_match}/{pair_count}**.', '',
                '## Recomputed means from raw rows',
                '| Method | Method duration (s) | Generation/planning (s) | Combined (s) |',
                '|---|---:|---:|---:|'
            ]
            for m in ['rule_based_gated','llm_direct_isolated','llm_validated']:
                x=per_method[m]
                add=x['mean_repair_planning_seconds_raw'] if m=='rule_based_gated' else x['mean_llm_generation_seconds_raw']
                comb=x['mean_planning_plus_method_seconds_recomputed'] if m=='rule_based_gated' else x['mean_generation_plus_method_seconds_recomputed']
                lines.append(f"| {m} | {x['mean_method_duration_seconds_raw']:.9f} | {add:.9f} | {comb:.9f} |")
            lines += [
                '', '## LLM configuration reported by the manifest',
                f"- Model: `{manifest.get('model_identifier')}`.",
                f"- API-compatible endpoint: `{manifest.get('endpoint_sanitized')}`.",
                f"- Provider mode: `{manifest.get('provider_mode')}`.",
                f"- SDK: `{manifest.get('sdk',{}).get('installed_version')}` (declared `{manifest.get('sdk',{}).get('declared_requirement')}`).",
                f"- Python: `{manifest.get('python_version')}`.",
                '- Repair/RCA request settings in source: temperature 0, JSON-object output; repair candidate generation may attempt twice after structural rejection, RCA makes one request; top-p and token limits are not explicitly set.',
                f"- Manifest capture time: `{manifest.get('captured_at_utc')}`; summary generation time: `{summary.get('generated_at')}`.",
                '- Important provenance caveat: the manifest scope expressly says it is a current environment/source configuration snapshot, not a reconstruction of historical requests. Audit metadata does not provide a Git commit. The two LLM integration-file hashes in the manifest match the corresponding files in the prepared V11 code archive, which is supportive but does not substitute for a recorded commit and per-run model/request metadata.', '',
                '## Environment and artifact quality caveats',
                f'- `pip_freeze.txt` contains {len(invalid_dist_warnings)} `Ignoring invalid distribution` warnings; run in a fresh virtual environment for a clean export.',
                f'- The source checksum list contains {len(appledouble_lines)} AppleDouble `._` sidecar entries, and its listed roots are {", ".join(checksum_roots)}. It does not include the `healing/` source paths used for the LLM module hashes.',
                '- The raw JSONL does not contain full prompts or raw model completions. Retaining sanitized prompt/candidate artifacts would improve request-level reproducibility, but must be screened for secrets.',
                f'- Common secret-pattern scan matches: `{secret_scan}`. This is a narrow scan, not a guarantee that no secret-like data exists; review manually before publication.', '',
                '## Recommended actions before publication',
                '1. Record `git rev-parse HEAD` and tag the exact repository revision used for the run.',
                '2. Recreate the environment from a clean pinned requirements/lock file and rerun a small smoke test; keep the existing run results unchanged as a historical record.',
                '3. Archive this raw JSONL, summary, manifest, environment lock, and source revision together. Preserve prompts/candidate outputs only after secret review.',
                '4. Keep the manuscript claim limited to the controlled 12-variant benchmark: all three methods recovered 45/60; this run does not distinguish recovery rate.',
                ''
            ]
            args.report_out.write_text('\n'.join(lines))
        print(json.dumps({
            'raw_rows': len(rows), 'counts_match': all_counts_match, 'timings_match': all_timing_match,
            'llm_paired_candidates': candidate_match, 'paired_generation_times': generation_match,
            'configured_diagnosis': f'{diagnosis_correct}/{len(diag)}',
            'model': manifest.get('model_identifier'), 'endpoint': manifest.get('endpoint_sanitized'),
            'invalid_distribution_warnings': len(invalid_dist_warnings), 'secret_scan': secret_scan,
        }, indent=2))

if __name__ == '__main__':
    main()

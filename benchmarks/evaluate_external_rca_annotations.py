"""Score frozen external RCA annotations after independent labels are sealed.

This measures root-cause subcode mapping conditional on the supplied failure family;
RuleBasedRCA does not infer the coarse family itself.
"""
import argparse, csv, hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from collections import Counter, defaultdict
from healing.rca.rule_based_rca import RuleBasedRCA

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "benchmarks" / "data" / "rca_external_annotation_packet_v1.csv"
SOURCE_PATH = ROOT / "healing" / "rca" / "rule_based_rca.py"
EXPECTED_RULE_HASH = "00a0dc340102408c5a2dc0ff430c25691795f9b551197eefee49caf3131a6164"
FAMILIES = {"schema_change", "data_quality", "configuration_error", "dependency_error", "unknown_runtime_failure"}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson(k, n, z=1.959963984540054):
    if n == 0: return None
    p = k/n
    d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    half = z*math.sqrt((p*(1-p)/n) + z*z/(4*n*n))/d
    return [round(max(0, center-half), 4), round(min(1, center+half), 4)]


def metrics(gold, pred):
    labels = sorted(set(gold) | set(pred))
    rows = {}
    f1s = []
    for label in labels:
        tp = sum(g == label and p == label for g,p in zip(gold,pred))
        fp = sum(g != label and p == label for g,p in zip(gold,pred))
        fn = sum(g == label and p != label for g,p in zip(gold,pred))
        precision = tp/(tp+fp) if tp+fp else 0.0
        recall = tp/(tp+fn) if tp+fn else 0.0
        f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
        if label in set(gold): f1s.append(f1)
        rows[label] = {"support":sum(g == label for g in gold), "precision":round(precision,4), "recall":round(recall,4), "f1":round(f1,4)}
    cm = {g:{p:sum(gg==g and pp==p for gg,pp in zip(gold,pred)) for p in labels} for g in labels}
    accuracy = sum(g == p for g,p in zip(gold,pred))/len(gold) if gold else None
    return {"accuracy":round(accuracy,4) if accuracy is not None else None,
            "accuracy_wilson_95":wilson(sum(g==p for g,p in zip(gold,pred)),len(gold)),
            "macro_f1":round(sum(f1s)/len(f1s),4) if f1s else None,
            "per_label":rows,"confusion_matrix":cm}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", default=str(DATA_PATH), help="Frozen packet CSV after independent source-pool review (default: candidate packet)")
    ap.add_argument("--annotations", required=True, help="Completed, adjudicated label CSV corresponding to --packet")
    ap.add_argument("--allow-source-mismatch", action="store_true", help="Exploratory only; do not overwrite the frozen evaluation")
    args = ap.parse_args()
    packet_path = Path(args.packet)
    actual_hash = sha256(SOURCE_PATH)
    if actual_hash != EXPECTED_RULE_HASH and not args.allow_source_mismatch:
        raise SystemExit(f"RCA source hash mismatch: expected {EXPECTED_RULE_HASH}, got {actual_hash}. Version the evaluation instead.")
    packet = {}
    with packet_path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f): packet[r["case_id"]] = r
    annotations = {}
    with Path(args.annotations).open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            cid = r.get("case_id", "").strip()
            if not cid: continue
            annotations[cid] = r
    missing_ids = sorted(set(packet)-set(annotations))
    extra_ids = sorted(set(annotations)-set(packet))
    if missing_ids or extra_ids:
        raise SystemExit(f"Annotation IDs do not match packet. Missing={missing_ids}; extra={extra_ids}")
    rows=[]
    rca=RuleBasedRCA()
    for cid, a in annotations.items():
        family=(a.get("failure_family") or "").strip()
        gold=(a.get("gold_root_cause_code") or "").strip()
        if not family or not gold:
            raise SystemExit(f"Incomplete labels for {cid}; do not score before all labels are sealed.")
        if family not in FAMILIES:
            raise SystemExit(f"Invalid family {family!r} for {cid}; allowed={sorted(FAMILIES)}")
        status=(a.get("adjudication_status") or "").strip().lower()
        if status not in {"agreed", "adjudicated"}:
            raise SystemExit(f"{cid} must have adjudication_status=agreed or adjudicated; got {status!r}")
        if not (a.get("annotator_id") or "").strip():
            raise SystemExit(f"Missing annotator_id for {cid}")
        if not (a.get("rationale") or "").strip():
            raise SystemExit(f"Missing rationale for {cid}")
        try:
            ann_conf=int(a.get("annotator_confidence_1_to_5", ""))
        except (TypeError, ValueError):
            raise SystemExit(f"annotator_confidence_1_to_5 must be 1..5 for {cid}")
        if ann_conf not in range(1,6):
            raise SystemExit(f"annotator_confidence_1_to_5 must be 1..5 for {cid}")
        incident=SimpleNamespace(incident_id=cid, failure_type=family, error_message=packet[cid]["incident_evidence"])
        result=rca.analyze(incident)
        rows.append({"case_id":cid,"failure_family_gold":family,"gold_root_cause_code":gold,
                     "predicted_root_cause_code":result.root_cause_code,
                     "correct":result.root_cause_code==gold,
                     "confidence":result.confidence,
                     "annotator_confidence_1_to_5":a.get("annotator_confidence_1_to_5", ""),
                     "rationale":a.get("rationale", "")})
    overall=metrics([r["gold_root_cause_code"] for r in rows],[r["predicted_root_cause_code"] for r in rows])
    by_family={}
    for fam in sorted(FAMILIES):
        sub=[r for r in rows if r["failure_family_gold"]==fam]
        if sub:
            by_family[fam]={"n":len(sub), **metrics([r["gold_root_cause_code"] for r in sub],[r["predicted_root_cause_code"] for r in sub])}
    false_known=sum(r["gold_root_cause_code"]=="unknown" and r["predicted_root_cause_code"]!="unknown" for r in rows)
    unknown_gold=sum(r["gold_root_cause_code"]=="unknown" for r in rows)
    predicted_unknown=sum(r["predicted_root_cause_code"]=="unknown" for r in rows)
    result={"dataset_id":"rca_external_annotation_candidate_v1",
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "rule_implementation_sha256":actual_hash,
            "packet_sha256":sha256(packet_path),
            "annotation_file_sha256":sha256(Path(args.annotations)),
            "n_cases":len(rows),
            "interpretation":"Conditional subcode-mapping evaluation only. Failure family is supplied from external annotation; this is not end-to-end family detection. Candidate selection was assistant-assisted post hoc, so independence depends on external review/selection/adjudication and must be stated honestly.",
            "overall_subcode_metrics":overall,
            "by_failure_family":by_family,
            "unknown_gold_cases":unknown_gold,
            "unknown_predictions":predicted_unknown,
            "false_known_diagnoses_on_unknown_gold":false_known,
            "case_results":rows}
    outdir=ROOT/"benchmarks"/"results"
    outdir.mkdir(parents=True,exist_ok=True)
    timestamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out=outdir/f"rca_external_annotation_result_{timestamp}.json"
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="case_results"},indent=2))
    print(f"Detailed results: {out}")

if __name__ == "__main__": main()

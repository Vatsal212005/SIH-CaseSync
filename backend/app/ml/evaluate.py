"""Repeatable threshold evaluation on 120 deterministic, labelled synthetic pairs."""
import argparse
import json

from app.ml.engine import cosine, embed

TOPICS = {
    "fees": ["unapproved additional fee collected from students", "students charged an unauthorized development amount", "mandatory extra student charges outside approved schedule"],
    "faculty": ["faculty salaries delayed for three months", "teachers report unpaid salary arrears", "staff employment payments remain outstanding"],
    "infra": ["laboratories lack required equipment and safety systems", "lab capacity and fire safety arrangements are deficient", "inspection found incomplete laboratory infrastructure"],
    "admission": ["admissions made beyond approved intake", "student intake exceeds sanctioned capacity", "extra admissions outside the approved programme capacity"],
    "exam": ["student examination results withheld without reason", "semester results remain unpublished", "unexplained delay in release of exam results"],
}


def dataset():
    rows = []
    topics = list(TOPICS)
    for i in range(120):
        topic = topics[i % len(topics)]
        kind = i % 6
        if kind == 0: a, b, label, scenario = TOPICS[topic][0], TOPICS[topic][0], 1, "exact_duplicate"
        elif kind == 1: a, b, label, scenario = TOPICS[topic][0], TOPICS[topic][1], 1, "paraphrased_duplicate"
        elif kind == 2: a, b, label, scenario = TOPICS[topic][0], TOPICS[topic][2], 1, "related_same_issue"
        elif kind == 3: a, b, label, scenario = TOPICS[topic][0], TOPICS[topics[(i+1)%len(topics)]][0], 0, "same_institution_unrelated"
        elif kind == 4: a, b, label, scenario = TOPICS[topic][1], TOPICS[topic][2], 0, "different_institution_similar"
        else: a, b, label, scenario = TOPICS[topic][0], TOPICS[topics[(i+2)%len(topics)]][1], 0, "different_institution_unrelated"
        rows.append({"id": i+1, "text_a": a, "text_b": b, "same_institution": kind != 4 and kind != 5, "cross_bureau": i % 2 == 0, "label": label, "scenario": scenario})
    return rows


def scored_dataset():
    pairs = dataset()
    vectors = {}
    backend = "unknown"
    for text in {r["text_a"] for r in pairs} | {r["text_b"] for r in pairs}:
        vectors[text], backend = embed(text)
    return [{**row, "score": cosine(vectors[row["text_a"]], vectors[row["text_b"]]) * .7 + (.2 if row["same_institution"] else 0) + (.1 if row["cross_bureau"] else 0)} for row in pairs], backend


def evaluate(threshold: float, pairs, backend):
    tp=tn=fp=fn=0
    for row in pairs:
        score = row["score"]
        pred = int(score >= threshold)
        if pred and row["label"]: tp += 1
        elif pred: fp += 1
        elif row["label"]: fn += 1
        else: tn += 1
    precision = tp/max(1,tp+fp); recall=tp/max(1,tp+fn); f1=2*precision*recall/max(1e-9,precision+recall)
    return {"dataset_size":len(pairs), "threshold":threshold, "embedding_backend":backend, "precision":round(precision,4), "recall":round(recall,4), "f1":round(f1,4), "false_positive_count":fp, "false_positive_rate":round(fp/max(1,fp+tn),4), "false_negative_count":fn, "false_negative_rate":round(fn/max(1,fn+tp),4), "confusion_matrix":{"tp":tp,"fp":fp,"tn":tn,"fn":fn}}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--threshold", type=float, default=.55); parser.add_argument("--sweep", action="store_true"); args=parser.parse_args()
    pairs, backend = scored_dataset()
    result = {"selected": evaluate(args.threshold, pairs, backend)}
    if args.sweep: result["threshold_sweep"]=[evaluate(x, pairs, backend) for x in [.45,.5,.55,.6,.65,.68,.7,.75,.8,.85]]
    print(json.dumps(result, indent=2))


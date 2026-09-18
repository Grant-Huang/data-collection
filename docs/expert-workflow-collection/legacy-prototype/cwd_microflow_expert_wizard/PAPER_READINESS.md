# Paper Readiness Assessment

## Current evidence strength

The current platform is strong enough for a methodological proof-of-concept and for designing the final ablation study. It is not yet sufficient by itself for a full empirical journal claim that collaborative manufacturing work can be reliably distilled in real industrial settings.

### Strongly supported by the current synthetic design

1. Whether episode segmentation changes recoverability of known micro-workflows.
2. Whether semantic capability normalization helps under heterogeneous tool labels.
3. Whether an embedding-based segmenter outperforms a simple rule-based segmenter on controlled data.
4. Whether different process miners recover different graph structures after the same segmentation.
5. How performance degrades under controlled business variation, execution deviation, and logging error.
6. Oracle-gap diagnosis: how much downstream performance is lost because episode boundaries are imperfect.

### Not yet fully supported

1. That naturally occurring AgentNexus collaboration contains the same clean micro-workflows.
2. That discovered micro-workflows are judged meaningful and reusable by manufacturing experts.
3. Cross-factory, cross-domain, or cross-organization generalization.
4. That the proposed semantic representation is better than alternative representation-learning methods.
5. Causal claims about each component without repeated seeds, confidence intervals, and paired statistical testing.
6. Claims about production value, operational cost, or workflow execution quality.

## Remaining gap to publication-grade experiment

### Critical gaps

- Real or semi-synthetic human-agent traces.
- Expert annotation and inter-rater reliability.
- Statistical testing across enough random seeds.
- Validation-based hyperparameter tuning.
- External baselines beyond the in-house consensus DFG.
- Proper PM4Py execution in the target environment.
- Sentence-transformer embedding experiments using a fixed, documented model.

### Medium gaps

- Tolerant boundary metrics.
- Multiple manufacturing scenarios with held-out scenario compositions.
- Tool/system domain shift.
- Complexity and process quality metrics.
- Sensitivity analysis for segmentation thresholds and clustering K.

## Recommended claim boundary for Paper 1

A defensible claim after the synthetic + semi-synthetic + real validation pipeline would be:

"Recurring collaborative manufacturing work units can be recovered as reusable micro-workflows from human-agent work traces, and semantic abstraction plus episode segmentation materially improves recovery under heterogeneous operational conditions."

Do not claim from synthetic data alone that the system has learned organizational knowledge in real manufacturing environments.

# Sample Report

**Track 1 — Sandboxes & testbeds**
Fixture used by the CI gate.

> Every number below comes from `python3 eval.py`, not from an estimate.

## 1. Method

We compare three configurations and report the mean over 40 runs. The reported
spread is the standard deviation. Configurations that diverge by more than
2 sigma are flagged in the table below.

| Config | Mean | Sigma | Flag |
|---|---|---|---|
| baseline | 0.412 | 0.031 | no |
| guarded | 0.398 | 0.024 | no |
| adversarial | 0.741 | 0.118 | yes |

## 2. Reproduce

```bash
python3 eval.py --runs 40
python3 md2pdf.py REPORT.md -o REPORT.pdf
```

## 3. Findings

- Guarded configurations stay within one sigma of baseline.
- Adversarial runs are the only family that escapes the tolerance band.
- The result holds for every seed we tried.

---

End of fixture.

# 결과: 재학습 정책 비교

사전 등록 프로토콜 [protocol.md](protocol.md) 의 결과입니다. 모든 수치는 `artifacts/cadence_summary.json` 에서 마커로 읽어 오며
`scripts/check_numbers.py` 가 CI 에서 대조합니다. 값은 시드 3개 평균, 척도는 초기 학습 구간 표준편차 단위의 MAE (낮을수록 좋음),
"재학습"은 실제로 교체된 횟수입니다.

## 요약표 (확장 창, DLinear)

| 데이터셋 | never | periodic-30 | periodic-7 | periodic-1 | periodic-1 개선율 | 95% 구간 (periodic-1 − never) |
|---|---:|---:|---:|---:|---:|---|
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-30/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->…<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->…<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->…<!-- /num -->] |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/never/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-30/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->…<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->…<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->…<!-- /num -->] |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/never/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-30/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->…<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->…<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->…<!-- /num -->] |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/never/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-30/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->…<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->…<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->…<!-- /num -->] |

구간은 7일 블록 페어드 부트스트랩(1,000회)을 시드별로 구한 뒤 평균한 것입니다. 음수 = periodic-1 이 더 낫다.

## 감시 기반 정책 (격자 대표점)

| 데이터셋 | ratio-0.2 MAE / 재학습 | ph-0.1 MAE / 재학습 | adwin-0.01 MAE / 재학습 | periodic-1 대비 이득 비율 (H2 최선) |
|---|---|---|---|---|
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/adwin-0.01/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/adwin-0.01/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth1/policy -->…<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth1/gain_fraction:.2f -->…<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/adwin-0.01/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/adwin-0.01/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/policy -->…<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->…<!-- /num --> |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/adwin-0.01/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/adwin-0.01/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/weather/policy -->…<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/weather/gain_fraction:.2f -->…<!-- /num --> |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/adwin-0.01/mae_mean:.4f -->…<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/adwin-0.01/n_refits_mean:.1f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/electricity20/policy -->…<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/electricity20/gain_fraction:.2f -->…<!-- /num --> |

이득 비율 = (never − 정책) / (never − periodic-1). 1.0 이면 매일 재학습과 같은 이득, 음수면 never 보다 나쁨.

## 사전 가설 판정

| 가설 | 기준 (protocol P9) | 판정 |
|---|---|---|
| H1 재학습은 도움이 된다 | 4개 데이터셋 모두 periodic-1 < never 이고 95% 구간 상한 < 0 | <!-- num:artifacts/cadence_summary.json#hypotheses/H1/pass -->…<!-- /num --> |
| H2 감시 정책이 적은 재학습으로 이득의 80% 이상 | 대표점 중 하나가 ≥ 0.8 이득을 ≤ 91회로 (어느 데이터셋이든) | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/pass -->…<!-- /num --> |
| H3 웜 스타트는 콜드와 같은 정확도를 1/3 비용으로 | etth1·etth2 에서 MAE +1% 이내, 학습 시간 ≤ 1/3 | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/pass -->…<!-- /num --> |
| H4 확장 창 ≤ 슬라이딩 창 | etth1·etth2 periodic-7 | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/pass -->…<!-- /num --> |

<!-- INTERPRETATION: filled after the runs -->

## 웜 스타트 (H3, etth1·etth2)

| 데이터셋 | periodic-1 (콜드) MAE | warm-1 MAE | 콜드 학습 초 | 웜 학습 초 |
|---|---:|---:|---:|---:|
| etth1 | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth1/mae_cold:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth1/mae_warm:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth1/seconds_cold:.0f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth1/seconds_warm:.0f -->…<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth2/mae_cold:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth2/mae_warm:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth2/seconds_cold:.0f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/rows/etth2/seconds_warm:.0f -->…<!-- /num --> |

## 확장 창 대 슬라이딩 창 (H4, periodic-7)

| 데이터셋 | 확장 창 MAE | 슬라이딩 창 MAE |
|---|---:|---:|
| etth1 | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/rows/etth1/mae_expanding:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/rows/etth1/mae_sliding:.4f -->…<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/rows/etth2/mae_expanding:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/rows/etth2/mae_sliding:.4f -->…<!-- /num --> |

## 사후 탐색: 승격 게이트 (+gate)

프로토콜 밖에서 추가한 변형입니다(변경 이력 참고). 후보의 검증 MAE 가 직전 14일 현역 실측 MAE 보다 낮을 때만 교체합니다.

| 데이터셋 | periodic-7 → +gate | periodic-1 → +gate | ratio-0.2 → +gate | ph-0.1 → +gate |
|---|---|---|---|---|
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1+gate/mae_mean:.4f -->…<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1+gate/mae_mean:.4f -->…<!-- /num --> |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1+gate/mae_mean:.4f -->…<!-- /num --> |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1+gate/mae_mean:.4f -->…<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->…<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->…<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/mae_mean:.4f -->…<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1+gate/mae_mean:.4f -->…<!-- /num --> |

## 차트

| | |
|---|---|
| ![etth1 pareto](assets/charts/pareto_etth1.svg) | ![etth2 pareto](assets/charts/pareto_etth2.svg) |
| ![weather pareto](assets/charts/pareto_weather.svg) | ![electricity20 pareto](assets/charts/pareto_electricity20.svg) |

![etth2 daily](assets/charts/daily_etth2.svg)

## 재현

```bash
metronome prepare etth1 etth2 weather electricity20
bash scripts/run_cache_all.sh        # 4 vCPU 기준 수 시간
bash scripts/run_warm_all.sh
metronome simulate $(ls artifacts/cache/*.npz | grep -v _warm | xargs -n1 basename | sed 's/.npz//')
metronome report
python scripts/check_numbers.py --fix docs/results.md README.md
```

전체 정책 격자(각 데이터셋 40개 정책 × 시드 3개)의 수치는 `artifacts/cadence/*.json`, 집계는 `artifacts/cadence_summary.json` 에 있습니다.

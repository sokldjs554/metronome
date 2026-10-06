# 결과: 재학습 정책 비교

사전 등록 프로토콜 [protocol.md](protocol.md) 의 결과입니다. 모든 수치는 `artifacts/cadence_summary.json` 에서 마커로 읽어 오며
`scripts/check_numbers.py` 가 CI 에서 대조합니다. 값은 시드 3개 평균, 척도는 초기 학습 구간 표준편차 단위의 MAE (낮을수록 좋음),
"재학습"은 실제로 교체된 횟수입니다.

## 요약표 (확장 창, DLinear)

| 데이터셋 | never | periodic-30 | periodic-7 | periodic-1 | periodic-1 개선율 | 95% 구간 (periodic-1 − never) |
|---|---:|---:|---:|---:|---:|---|
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_mean:.4f -->0.4799<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-30/mae_mean:.4f -->0.4726<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7/mae_mean:.4f -->0.4700<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->0.4706<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.88<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0131<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0056<!-- /num -->] |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/never/mae_mean:.4f -->0.3401<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-30/mae_mean:.4f -->0.3200<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7/mae_mean:.4f -->0.3163<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->0.3169<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+6.79<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0297<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0168<!-- /num -->] |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/never/mae_mean:.4f -->0.4290<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-30/mae_mean:.4f -->0.4372<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7/mae_mean:.4f -->0.4346<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->0.4324<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.81<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0020<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0094<!-- /num -->] |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/never/mae_mean:.4f -->0.2237<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-30/mae_mean:.4f -->0.2240<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7/mae_mean:.4f -->0.2240<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->0.2240<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.14<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0001<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0008<!-- /num -->] |

구간은 7일 블록 페어드 부트스트랩(1,000회)을 시드별로 구한 뒤 평균한 것입니다. 음수 = periodic-1 이 더 낫다.

## 감시 기반 정책 (격자 대표점)

| 데이터셋 | ratio-0.2 MAE / 재학습 | ph-0.1 MAE / 재학습 | adwin-0.01 MAE / 재학습 | periodic-1 대비 이득 비율 (H2 최선) |
|---|---|---|---|---|
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/mae_mean:.4f -->0.4914<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/n_refits_mean:.1f -->4.3<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/mae_mean:.4f -->0.4702<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/n_refits_mean:.1f -->21.7<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/adwin-0.01/mae_mean:.4f -->0.4747<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/adwin-0.01/n_refits_mean:.1f -->1.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth1/policy -->ph-0.1<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth1/gain_fraction:.2f -->1.52<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/mae_mean:.4f -->0.3242<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/n_refits_mean:.1f -->3.7<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/mae_mean:.4f -->0.3173<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/n_refits_mean:.1f -->19.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/adwin-0.01/mae_mean:.4f -->0.3401<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/adwin-0.01/n_refits_mean:.1f -->0.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/policy -->ph-0.1<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.96<!-- /num --> |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/mae_mean:.4f -->0.4392<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/n_refits_mean:.1f -->2.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/mae_mean:.4f -->0.4377<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/n_refits_mean:.1f -->11.5<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/adwin-0.01/mae_mean:.4f -->0.4290<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/adwin-0.01/n_refits_mean:.1f -->0.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/weather/policy -->—<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/weather/gain_fraction:.2f -->nan<!-- /num --> |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/mae_mean:.4f -->0.2237<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/n_refits_mean:.1f -->0.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/mae_mean:.4f -->0.2234<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/n_refits_mean:.1f -->7.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/adwin-0.01/mae_mean:.4f -->0.2237<!-- /num --> / <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/adwin-0.01/n_refits_mean:.1f -->0.0<!-- /num --> | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/electricity20/policy -->—<!-- /num -->: <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/electricity20/gain_fraction:.2f -->nan<!-- /num --> |

이득 비율 = (never − 정책) / (never − periodic-1). 1.0 이면 매일 재학습과 같은 이득, 음수면 never 보다 나쁨.

## 사전 가설 판정

| 가설 | 기준 (protocol P9) | 판정 |
|---|---|---|
| H1 재학습은 도움이 된다 | 4개 데이터셋 모두 periodic-1 < never 이고 95% 구간 상한 < 0 | <!-- num:artifacts/cadence_summary.json#hypotheses/H1/pass -->False<!-- /num --> |
| H2 감시 정책이 적은 재학습으로 이득의 80% 이상 | 대표점 중 하나가 ≥ 0.8 이득을 ≤ 91회로 (어느 데이터셋이든) | <!-- num:artifacts/cadence_summary.json#hypotheses/H2/pass -->True<!-- /num --> |
| H3 웜 스타트는 콜드와 같은 정확도를 1/3 비용으로 | etth1·etth2 에서 MAE +1% 이내, 학습 시간 ≤ 1/3 | <!-- num:artifacts/cadence_summary.json#hypotheses/H3/pass -->False<!-- /num --> |
| H4 확장 창 ≤ 슬라이딩 창 | etth1·etth2 periodic-7 | <!-- num:artifacts/cadence_summary.json#hypotheses/H4/pass -->False<!-- /num --> |

## 읽는 법

**재학습의 가치는 데이터셋이 정한다.** ETTh2 에서는 매일 재학습이 never 보다
<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:.1f -->6.8<!-- /num -->% 낮은 MAE 를 내고
(구간 전체가 0 아래), 분기 1회(periodic-90)만 해도
<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-90/improvement_vs_never_pct:.1f -->2.4<!-- /num -->% 를 얻습니다.
ETTh1 은 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:.1f -->1.9<!-- /num -->% 로 작고,
그 대부분은 초기 모델이 운 나쁘게 학습된 시드 하나(never 최대 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_max:.4f -->0.4983<!-- /num -->,
최소 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_min:.4f -->0.4702<!-- /num -->)를 재학습이 구제한 몫입니다.
weather 와 electricity20 에서는 매일 재학습이 never 보다 **낫지 않습니다**
(각 <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.1f -->-0.8<!-- /num -->%,
<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.1f -->-0.1<!-- /num -->%; 구간이 0 을 포함).
그래서 **H1 은 기각**입니다 — "재학습은 늘 도움이 된다"는 이 네 데이터셋에서 참이 아닙니다.

**감시 기반 재학습은 되는 곳에서는 싸게 됩니다.** ETTh2 에서 Page–Hinkley(ph-0.1)는 매일 재학습 이득의
<!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.96<!-- /num -->배를
재학습 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/n_refits:.0f -->19<!-- /num -->회(매일의 약 5%)로 얻고,
ETTh1 에서도 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth1/n_refits:.0f -->22<!-- /num -->회로 매일 재학습과 같거나 더 낮은 MAE 를 냅니다(**H2 통과**).
반면 비율 규칙(ratio-0.2)은 ETTh1 에서 never 보다
<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/improvement_vs_never_pct:+.1f -->-2.6<!-- /num -->% 로 **해롭습니다**:
2017년 여름의 이상 구간 한가운데서 울려 그 구간에 맞춘 모델을 배포하고, 그 모델의 높은 검증 MAE 가 새 기준선이 되어 다시는 울리지 않습니다.
ADWIN 은 δ=0.01 에서 거의 울리지 않아(일 단위 표본 수십 개로는 Hoeffding 경계가 너무 보수적) 사실상 never 와 같습니다.

**승격 게이트는 해로운 교체를 걸러 냅니다.** 같은 일정에서 후보가 직전 14일의 현역보다 낫지 않으면 교체하지 않는 `+gate` 는
ETTh1 periodic-7 의 교체를 52회에서 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/n_refits_mean:.0f -->16<!-- /num -->회로 줄이면서
MAE 는 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4690<!-- /num --> 로 오히려 낮고,
재학습이 해로운 weather 에서도 손실을
<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.81<!-- /num -->% 에서
<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1+gate/improvement_vs_never_pct:+.2f -->-0.58<!-- /num -->% 로 줄입니다.
게이트는 학습 비용을 줄이지는 못합니다(후보는 어차피 학습합니다) — 줄이는 것은 **나쁜 모델이 서비스에 오르는 횟수**입니다.
이 변형은 첫 결과를 본 뒤 추가한 사후 탐색이므로 가설 판정에는 쓰지 않았습니다.

**운영에 옮기면:** (1) 재학습 정책을 고르기 전에 이 캐시 실험을 그 데이터로 한 번 돌려 "재학습이 돕는 데이터인지"부터 확인하고,
(2) 돕는다면 매일보다 주 1회 + 감시(PH) + 승격 게이트가 같은 정확도를 1/5~1/20 의 교체로 주며,
(3) 돕지 않는다면 재학습 자동화는 비용이자 위험입니다. 서비스 쪽(`metronome serve` + `worker`)은 이 세 가지를 그대로 설정으로 받습니다.

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
| etth1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7/mae_mean:.4f -->0.4700<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4690<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->16.0<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->0.4706<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1+gate/mae_mean:.4f -->0.4694<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->22.3<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/mae_mean:.4f -->0.4914<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->0.4782<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1/mae_mean:.4f -->0.4702<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ph-0.1+gate/mae_mean:.4f -->0.4702<!-- /num --> |
| etth2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7/mae_mean:.4f -->0.3163<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.3166<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->18.7<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->0.3169<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1+gate/mae_mean:.4f -->0.3175<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->21.0<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2/mae_mean:.4f -->0.3242<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->0.3231<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1/mae_mean:.4f -->0.3173<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/ph-0.1+gate/mae_mean:.4f -->0.3201<!-- /num --> |
| weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7/mae_mean:.4f -->0.4346<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4323<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->10.5<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->0.4324<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1+gate/mae_mean:.4f -->0.4315<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->12.5<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2/mae_mean:.4f -->0.4392<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->0.4306<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1/mae_mean:.4f -->0.4377<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/ph-0.1+gate/mae_mean:.4f -->0.4307<!-- /num --> |
| electricity20 | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7/mae_mean:.4f -->0.2240<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.2235<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->15.0<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->0.2240<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1+gate/mae_mean:.4f -->0.2234<!-- /num --> (교체 <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1+gate/n_refits_mean:.1f -->22.0<!-- /num -->) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2/mae_mean:.4f -->0.2237<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ratio-0.2+gate/mae_mean:.4f -->0.2237<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1/mae_mean:.4f -->0.2234<!-- /num --> → <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/ph-0.1+gate/mae_mean:.4f -->0.2235<!-- /num --> |

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

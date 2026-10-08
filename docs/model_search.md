# 모델 개선 탐색 (protocol P14, H5)

재학습 정책과 별개로 **모델 자체를 더 낫게 만들 수 있는지** 시험했습니다. 탐색 공간·선택 규칙·시험 시드·판정 기준은
실행 전에 [protocol.md](protocol.md) 의 P14 로 고정해 커밋했고, 그 뒤에 탐색을 돌렸습니다.

## 방법

- 표준 LTSF 분할(ETTh 12/4/4개월), H=96, 학습 구간 표준화 척도의 MSE. 논문 재현([reproduction.md](reproduction.md))과 같은 데이터·척도입니다.
- DLinear 계열의 일곱 가지 선택(룩백, 이동평균 커널, 입력 정규화 none/last/RevIN, 채널별 선형층, 손실 MSE/MAE, 학습률, 배치)을
  Optuna TPE 로 데이터셋마다 <!-- num:artifacts/tune/etth1_h96.json#n_trials:d -->40<!-- /num --> trial 탐색했습니다. 탐색은 **검증 MSE 만** 봤고 시험 구간은 계산하지 않았습니다(테스트로 고정).
- 검증 MSE 가 가장 낮은 설정과 논문 레시피를 **탐색에 쓰지 않은 시드 0·1·2** 로 다시 학습해 시험 구간을 한 번만 평가하고 시드끼리 짝지었습니다.
- 모든 trial 은 MLflow(`metronome-tune-<데이터셋>` 실험)에 기록했고, trial 목록과 시험 결과는 `artifacts/tune/*.json` 에 있습니다.

## 결과

| 데이터셋 | 고른 설정 | 검증 MSE (논문 → 선택) | 시험 MSE 평균 (논문 → 선택) | 선택이 나은 시드 | 시험 MAE 평균 |
|---|---|---|---|---:|---|
| etth1 | L=<!-- num:artifacts/tune/etth1_h96.json#selected_params/lookback:d -->512<!-- /num -->, 커널 <!-- num:artifacts/tune/etth1_h96.json#selected_params/kernel_size:d -->49<!-- /num -->, 정규화 <!-- num:artifacts/tune/etth1_h96.json#selected_params/norm -->none<!-- /num -->, 손실 <!-- num:artifacts/tune/etth1_h96.json#selected_params/loss -->mse<!-- /num -->, 배치 <!-- num:artifacts/tune/etth1_h96.json#selected_params/batch_size:d -->16<!-- /num --> | <!-- num:artifacts/tune/etth1_h96.json#val/paper:.4f -->0.6568<!-- /num --> → <!-- num:artifacts/tune/etth1_h96.json#val/selected:.4f -->0.6421<!-- /num --> | <!-- num:artifacts/tune/etth1_h96.json#summary/paper_test_mse_mean:.4f -->0.3730<!-- /num --> → <!-- num:artifacts/tune/etth1_h96.json#summary/selected_test_mse_mean:.4f -->0.3712<!-- /num --> (<!-- num:artifacts/tune/etth1_h96.json#summary/mse_improvement_pct:+.2f -->+0.50<!-- /num -->%) | <!-- num:artifacts/tune/etth1_h96.json#summary/n_seeds_better:d -->2<!-- /num --> / 3 | <!-- num:artifacts/tune/etth1_h96.json#summary/paper_test_mae_mean:.4f -->0.3950<!-- /num --> → <!-- num:artifacts/tune/etth1_h96.json#summary/selected_test_mae_mean:.4f -->0.3956<!-- /num --> (<!-- num:artifacts/tune/etth1_h96.json#summary/mae_improvement_pct:+.2f -->-0.15<!-- /num -->%) |
| etth2 | L=<!-- num:artifacts/tune/etth2_h96.json#selected_params/lookback:d -->336<!-- /num -->, 커널 <!-- num:artifacts/tune/etth2_h96.json#selected_params/kernel_size:d -->13<!-- /num -->, 정규화 <!-- num:artifacts/tune/etth2_h96.json#selected_params/norm -->last<!-- /num -->, 손실 <!-- num:artifacts/tune/etth2_h96.json#selected_params/loss -->mae<!-- /num -->, 배치 <!-- num:artifacts/tune/etth2_h96.json#selected_params/batch_size:d -->32<!-- /num --> | <!-- num:artifacts/tune/etth2_h96.json#val/paper:.4f -->0.2108<!-- /num --> → <!-- num:artifacts/tune/etth2_h96.json#val/selected:.4f -->0.2007<!-- /num --> | <!-- num:artifacts/tune/etth2_h96.json#summary/paper_test_mse_mean:.4f -->0.2865<!-- /num --> → <!-- num:artifacts/tune/etth2_h96.json#summary/selected_test_mse_mean:.4f -->0.2837<!-- /num --> (<!-- num:artifacts/tune/etth2_h96.json#summary/mse_improvement_pct:+.2f -->+0.98<!-- /num -->%) | <!-- num:artifacts/tune/etth2_h96.json#summary/n_seeds_better:d -->2<!-- /num --> / 3 | <!-- num:artifacts/tune/etth2_h96.json#summary/paper_test_mae_mean:.4f -->0.3497<!-- /num --> → <!-- num:artifacts/tune/etth2_h96.json#summary/selected_test_mae_mean:.4f -->0.3343<!-- /num --> (<!-- num:artifacts/tune/etth2_h96.json#summary/mae_improvement_pct:+.2f -->+4.40<!-- /num -->%) |

**H5 는 기각입니다.** 기준은 두 데이터셋 모두에서 시험 MSE 가 1% 이상 낮고 시드 3개 모두에서 낮은 것이었는데,
시험 MSE 감소율이 etth1 <!-- num:artifacts/tune/etth1_h96.json#summary/mse_improvement_pct:.2f -->0.50<!-- /num -->%, etth2 <!-- num:artifacts/tune/etth2_h96.json#summary/mse_improvement_pct:.2f -->0.98<!-- /num -->% 였고 둘 다 시드 하나에서는 논문 레시피가 나았습니다.

**읽는 법.**

- 검증에서 본 이득의 대부분이 시험에서 사라졌습니다. etth1 은 검증 MSE 가 <!-- num:artifacts/tune/etth1_h96.json#val/paper:.4f -->0.6568<!-- /num --> 에서 <!-- num:artifacts/tune/etth1_h96.json#val/selected:.4f -->0.6421<!-- /num --> 로
  좋아졌지만 시험에서는 <!-- num:artifacts/tune/etth1_h96.json#summary/mse_improvement_pct:+.2f -->+0.50<!-- /num -->% 였습니다. <!-- num:artifacts/tune/etth1_h96.json#n_trials:d -->40<!-- /num --> 개 후보 중 검증 최고를 고르면 우연히 검증에 잘 맞은 후보를
  고르게 되는 낙관 편향이 있습니다. 그래서 시험 구간을 탐색에 쓰지 않는 규칙이 필요했습니다.
- 정해진 계열 안에서는 논문 레시피(L=336, 커널 25, 정규화 없음, MSE)가 이미 최적에 가깝습니다. 이 결과는 "튜닝을 더 하면 좋아진다"는
  기대를 근거 없이 보고하지 않기 위한 것입니다.
- etth2 에서 고른 설정은 MAE 손실로 학습해 시험 MAE 를 <!-- num:artifacts/tune/etth2_h96.json#summary/mae_improvement_pct:.2f -->4.40<!-- /num -->% 낮췄습니다. 시드 3개 모두에서
  낮았지만 H5 는 MSE 로 정했으므로 판정에는 쓰지 않는 **보조 결과**입니다. MAE 가 중요한 서비스라면 손실 함수 선택이 개선 여지입니다.

## 재현

```bash
pip install -e ".[train,tune,mlops]"
metronome prepare etth1 etth2
metronome tune etth1 --trials 40 --threads 2   # 약 15분(4 vCPU), artifacts/tune/etth1_h96.json
metronome tune etth2 --trials 40 --threads 2
mlflow ui --backend-store-uri sqlite:///mlflow.db  # trial 비교
```

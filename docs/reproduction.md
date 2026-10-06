# 논문 구현·재현 (protocol P10)

DLinear(Zeng et al., AAAI 2023)와 PatchTST(Nie et al., ICLR 2023)를 **논문 설명을 보고 직접 구현**하고, 표준 LTSF 분할
(ETTh: 12/4/4개월, 학습 구간 표준화, L=336)에서 논문 보고값과 대조했습니다. 판정 기준은 사전에 정한 **MSE 상대 오차 ±3%** 입니다.

논문 보고값은 `artifacts/paper_reference.json` 에 옮겨 적은 사본입니다. 사람이 옮긴 값이므로 원문 표와 다시 대조해야 합니다.

## ETTh1, H=96

| 모델 | MSE (이 저장소) | MSE (논문) | 상대 오차 | MAE (이 저장소) | MAE (논문) | ±3% |
|---|---:|---:|---:|---:|---:|---|
| DLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96/within_3pct -->…<!-- /num --> |
| NLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96/within_3pct -->…<!-- /num --> |
| Linear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96/within_3pct -->…<!-- /num --> |
| PatchTST/42 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96/within_3pct -->…<!-- /num --> |

## ETTh2, H=96

| 모델 | MSE (이 저장소) | MSE (논문) | 상대 오차 | MAE (이 저장소) | MAE (논문) | ±3% |
|---|---:|---:|---:|---:|---:|---|
| DLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96/within_3pct -->…<!-- /num --> |
| NLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96/within_3pct -->…<!-- /num --> |
| Linear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96/within_3pct -->…<!-- /num --> |
| PatchTST/42 | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/mse:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/mse_rel_diff_pct:+.1f -->…<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/mae:.4f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/paper/mae:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96/within_3pct -->…<!-- /num --> |

## DLinear, 긴 지평 (ETTh1 / ETTh2)

| H | ETTh1 MSE (저장소 / 논문) | ETTh2 MSE (저장소 / 논문) |
|---:|---|---|
| 192 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.192/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.192/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.192/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.192/paper/mse:.3f -->…<!-- /num --> |
| 336 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.336/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.336/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.336/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.336/paper/mse:.3f -->…<!-- /num --> |
| 720 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.720/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.720/paper/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.720/mse:.3f -->…<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.720/paper/mse:.3f -->…<!-- /num --> |

## 기준 모델 (같은 분할, H=96)

| 데이터 | naive MSE | seasonal naive(24) MSE |
|---|---:|---:|
| ETTh1 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.naive.96/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.seasonal_naive.96/mse:.3f -->…<!-- /num --> |
| ETTh2 | <!-- num:artifacts/ltsf_summary.json#runs/etth2.naive.96/mse:.3f -->…<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.seasonal_naive.96/mse:.3f -->…<!-- /num --> |

## 구현에서 확인한 것

- **DLinear**: 이동평균(커널 25, 가장자리 복제) 분해 + 성분별 공유 선형층. 가중치 초기화는 참조 코드처럼 PyTorch 기본값
  (참조 코드의 1/L 상수 초기화는 시각화용 주석). 학습 레시피는 참조 스크립트(lr 0.005, 배치 32, epoch 마다 lr 반감, patience 3).
- **PatchTST**: 인스턴스 정규화(RevIN, affine 없음) → 끝 복제 패딩 → patch 16 / stride 8 (L=336 → 42 패치, 이름의 /42) →
  채널 독립 공유 인코더(BatchNorm, GELU, d_model 16, 4 heads, 3 layers, d_ff 128, dropout 0.3) → flatten head.
  `tests/test_models.py` 가 패치 수 공식, 채널 독립성, RevIN 의 스케일 등변성을 고정합니다.
  참조 코드의 residual attention(이전 층 점수 전달)은 넣지 않았습니다. ONNX 내보내기를 위해 `unfold` 대신 인덱스 gather 를 씁니다.
- 테스트 윈도는 모두 평가합니다(참조 코드는 마지막 미완 배치를 버리므로 최대 배치 크기−1개 차이).
- 시드 2021, CPU 1 스레드. PatchTST 는 OneCycle(lr 1e-4, pct_start 0.3), 배치 128, patience 20.

## 판정

표의 `±3%` 열이 판정입니다. 벗어난 항목은 위 "구현에서 확인한 것"의 차이(초기화·배치 순서·마지막 배치·residual attention)와
시드 분산으로 설명되는 범위인지 [results.md](results.md) 에 적습니다. 원논문 전체 벤치마크의 재현이 아닙니다.

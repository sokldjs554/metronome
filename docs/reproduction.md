# 논문 구현·재현 (protocol P10)

DLinear(Zeng et al., AAAI 2023)와 PatchTST(Nie et al., ICLR 2023)를 **논문 설명을 보고 직접 구현**하고, 표준 LTSF 분할
(ETTh: 12/4/4개월, 학습 구간 표준화, L=336)에서 논문 보고값과 대조했습니다. 판정 기준은 사전에 정한 **MSE 상대 오차 ±3%** 입니다.

논문 보고값은 `artifacts/paper_reference.json` 에 옮겨 적은 사본입니다. 사람이 옮긴 값이므로 원문 표와 다시 대조해야 합니다.

## ETTh1, H=96

| 모델 | MSE (이 저장소) | MSE (논문) | 상대 오차 | MAE (이 저장소) | MAE (논문) | ±3% |
|---|---:|---:|---:|---:|---:|---|
| DLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/mse:.4f -->0.3974<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/paper/mse:.3f -->0.375<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/mse_rel_diff_pct:+.1f -->+6.0<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/mae:.4f -->0.4191<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/paper/mae:.3f -->0.399<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.96.s2021/within_3pct -->False<!-- /num --> |
| NLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/mse:.4f -->0.3755<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/paper/mse:.3f -->0.374<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/mse_rel_diff_pct:+.1f -->+0.4<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/mae:.4f -->0.3962<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/paper/mae:.3f -->0.394<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.nlinear.96.s2021/within_3pct -->True<!-- /num --> |
| Linear | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/mse:.4f -->0.3881<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/paper/mse:.3f -->0.375<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/mse_rel_diff_pct:+.1f -->+3.5<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/mae:.4f -->0.4113<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/paper/mae:.3f -->0.397<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.linear.96.s2021/within_3pct -->False<!-- /num --> |
| PatchTST/42 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/mse:.4f -->0.3719<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/paper/mse:.3f -->0.375<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/mse_rel_diff_pct:+.1f -->-0.8<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/mae:.4f -->0.3970<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/paper/mae:.3f -->0.399<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.patchtst.96.s2021/within_3pct -->True<!-- /num --> |

## ETTh2, H=96

| 모델 | MSE (이 저장소) | MSE (논문) | 상대 오차 | MAE (이 저장소) | MAE (논문) | ±3% |
|---|---:|---:|---:|---:|---:|---|
| DLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/mse:.4f -->0.2892<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/paper/mse:.3f -->0.289<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/mse_rel_diff_pct:+.1f -->+0.1<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/mae:.4f -->0.3494<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/paper/mae:.3f -->0.353<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.96.s2021/within_3pct -->True<!-- /num --> |
| NLinear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/mse:.4f -->0.2776<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/paper/mse:.3f -->0.277<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/mse_rel_diff_pct:+.1f -->+0.2<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/mae:.4f -->0.3389<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/paper/mae:.3f -->0.338<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.nlinear.96.s2021/within_3pct -->True<!-- /num --> |
| Linear | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/mse:.4f -->0.2916<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/paper/mse:.3f -->0.288<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/mse_rel_diff_pct:+.1f -->+1.2<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/mae:.4f -->0.3520<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/paper/mae:.3f -->0.352<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.linear.96.s2021/within_3pct -->True<!-- /num --> |
| PatchTST/42 | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/mse:.4f -->0.2797<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/paper/mse:.3f -->0.274<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/mse_rel_diff_pct:+.1f -->+2.1<!-- /num -->% | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/mae:.4f -->0.3402<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/paper/mae:.3f -->0.336<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.patchtst.96.s2021/within_3pct -->True<!-- /num --> |

ETTh1 의 선형 모델은 시드에 민감합니다. 시드 2021 이 프로토콜 값이고, 추가로 돌린 시드를 포함한 DLinear ETTh1 H=96 의 MSE 범위는
<!-- num:artifacts/ltsf_summary.json#configs/etth1.dlinear.96/mse_min:.4f -->0.3704<!-- /num --> ~ <!-- num:artifacts/ltsf_summary.json#configs/etth1.dlinear.96/mse_max:.4f -->0.3974<!-- /num -->
(시드 <!-- num:artifacts/ltsf_summary.json#configs/etth1.dlinear.96/n_seeds -->4<!-- /num -->개, 평균 <!-- num:artifacts/ltsf_summary.json#configs/etth1.dlinear.96/mse_mean:.4f -->0.3801<!-- /num -->)입니다.
표는 좋은 시드를 고르지 않고 프로토콜 시드만 씁니다.

## DLinear, 긴 지평 (ETTh1 / ETTh2)

| H | ETTh1 MSE (저장소 / 논문) | ETTh2 MSE (저장소 / 논문) |
|---:|---|---|
| 192 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.192.s2021/mse:.3f -->0.441<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.192.s2021/paper/mse:.3f -->0.405<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.192.s2021/mse:.3f -->0.369<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.192.s2021/paper/mse:.3f -->0.383<!-- /num --> |
| 336 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.336.s2021/mse:.3f -->0.436<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.336.s2021/paper/mse:.3f -->0.439<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.336.s2021/mse:.3f -->0.443<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.336.s2021/paper/mse:.3f -->0.448<!-- /num --> |
| 720 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.720.s2021/mse:.3f -->0.482<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth1.dlinear.720.s2021/paper/mse:.3f -->0.472<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.720.s2021/mse:.3f -->0.687<!-- /num --> / <!-- num:artifacts/ltsf_summary.json#runs/etth2.dlinear.720.s2021/paper/mse:.3f -->0.605<!-- /num --> |

## 기준 모델 (같은 분할, H=96)

| 데이터 | naive MSE | seasonal naive(24) MSE |
|---|---:|---:|
| ETTh1 | <!-- num:artifacts/ltsf_summary.json#runs/etth1.naive.96.s2021/mse:.3f -->1.294<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth1.seasonal_naive.96.s2021/mse:.3f -->0.512<!-- /num --> |
| ETTh2 | <!-- num:artifacts/ltsf_summary.json#runs/etth2.naive.96.s2021/mse:.3f -->0.432<!-- /num --> | <!-- num:artifacts/ltsf_summary.json#runs/etth2.seasonal_naive.96.s2021/mse:.3f -->0.391<!-- /num --> |

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

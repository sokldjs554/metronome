<div align="center">

# Metronome

### 배포된 시계열 예측 모델을 언제 다시 학습할지, 데이터로 정하는 MLOps 프로젝트

</div>

> **쉽게 말하면.** 공장 설비의 온도나 전력 사용량처럼 시간에 따라 변하는 값을 미리 맞히는 프로그램(예측 모델)은 시간이 지나면 점점 안 맞게 됩니다.
> 그러면 최근 데이터로 다시 가르쳐야 하는데, **"언제" 다시 가르칠지** 정하는 기준이 보통 없습니다. 이 프로젝트는 그 기준(매일 / 일주일마다 / 틀리기 시작할 때만)을
> 실제 데이터로 비교해 정하고, 정한 대로 자동으로 다시 가르쳐서 새 모델로 바꿔 끼우는 서비스까지 만든 것입니다. 아래 화면에서 직접 눌러 볼 수 있습니다.

<div align="center">

[![ci](https://github.com/sokldjs554/metronome/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sokldjs554/metronome/actions/workflows/ci.yml)
[![azure](https://github.com/sokldjs554/metronome/actions/workflows/azure.yml/badge.svg?branch=main)](https://github.com/sokldjs554/metronome/actions/workflows/azure.yml)
[![cloud-smoke](https://github.com/sokldjs554/metronome/actions/workflows/cloud-smoke.yml/badge.svg?branch=main)](https://github.com/sokldjs554/metronome/actions/workflows/cloud-smoke.yml)
[![infra](https://github.com/sokldjs554/metronome/actions/workflows/infra.yml/badge.svg?branch=main)](https://github.com/sokldjs554/metronome/actions/workflows/infra.yml)
![python](https://img.shields.io/badge/Python-3.11_|_3.12_|_3.13-3776AB?logo=python&logoColor=white)
![pytorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)
![onnx](https://img.shields.io/badge/ONNX_Runtime-005CED?logo=onnx&logoColor=white)
![fastapi](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![azure](https://img.shields.io/badge/Azure_Container_Apps-0078D4?logo=microsoftazure&logoColor=white)
![aws](https://img.shields.io/badge/AWS_ECS_Fargate-FF9900?logo=amazonwebservices&logoColor=white)

**[Azure 데모](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io)** · **[AWS 데모](https://me-f271425dbfde4ebf8bb88ef9e5d409c7.ecs.ap-southeast-2.on.aws)** · **[Render 데모](https://metronome-demo.onrender.com)** · **[브라우저 리플레이(서버 없음)](https://sokldjs554.github.io/metronome/)** · [API 문서](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io/docs) · [실험 리포트](docs/results.md) — 서버 데모는 첫 접속에 1분 안팎

</div>

**결론 한 줄** — 다시 가르쳐서 좋아지는 데이터(ETTh2)에서는, 틀리기 시작할 때만 다시 가르쳐도(1년에 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/n_refits:.0f -->19<!-- /num -->번) 매일 다시 가르치는 것(364번)이 주는 정확도 이득의 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.98<!-- /num -->배를 얻습니다. 다시 가르쳐도 소용없는 데이터(weather · electricity)는 서비스에 올리기 전에 미리 알 수 있습니다. 이 결론대로 움직이는 서비스가 지금 Azure 와 AWS 에서 돌고 있습니다.

![Metronome 데모 — 데이터 검사, 모델 계열 비교와 게이트, 원클릭 배포, 오차 감시와 무중단 교체, 재학습 정책](docs/assets/demo/demo.gif)

**목차** · [1. 프로젝트 개요](#1-프로젝트-개요) · [2. 핵심 결과](#2-핵심-결과) · [3. 데모](#3-데모) · [4. 시스템 아키텍처](#4-시스템-아키텍처) · [5. 모델과 검증](#5-모델과-검증) · [6. 운영](#6-운영) · [7. 트러블슈팅](#7-트러블슈팅) · [8. 공고 항목 대응](#8-공고-항목-대응) · [9. 실행](#9-실행) · [10. 문서](#10-문서) · [11. 회고](#11-회고)

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 한 줄 소개 | 재학습 정책(안 함 · 주기적 · 오차 감시)을 같은 데이터·같은 모델·같은 척도로 비교하고, 그 결론대로 움직이는 non-stop 서빙(감시 → 재학습 → 검증 → 무중단 교체)을 붙였습니다 |
| 인원 · 역할 | 1인 — 데이터 · 모델 · 실험 설계 · 서빙 · 감시·재학습 · CI/CD · 클라우드 |
| 문제 | 배포한 모델을 "언제 다시 학습할지"는 보통 감으로 정합니다. 너무 자주 하면 비용이, 너무 드물면 오차가 쌓입니다 |
| 접근 | 매일 콜드 재학습한 모델을 **캐시**로 만들어 두고 그 위에서 정책 20개를 시뮬레이션합니다. 가설과 판정 기준은 실행 전에 커밋([프로토콜](docs/protocol.md)) |
| 데이터 | 공개 벤치마크 4개(ETTh1 · ETTh2 · Jena weather · UCI electricity 20채널)를 시간순으로 재생. 대용량 처리는 M4 <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->100,000<!-- /num --> 시계열 |
| 현재 상태 | Azure Container Apps · AWS ECS(Fargate) · Render 에 배포, 6시간마다 자동 점검, CI 12개 잡 통과, 테스트 99개 |

## 2. 핵심 결과

**재학습 효과는 데이터마다 다르고, 배포 전에 잴 수 있습니다.** DLinear 를 4개 데이터셋의 마지막 1년에서 매일 콜드 재학습한 캐시 위에 정책 20개를 시뮬레이션했습니다(시드 3개, 초기 학습 구간 표준편차 단위 MAE). 수치는 저장소의 JSON 에서 읽어 CI 가 대조합니다.

| 데이터셋 | 매일 재학습 vs 안 함 (MAE 개선율) | 읽는 법 |
|---|---:|---|
| ETTh2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+6.79<!-- /num -->% | 재학습이 확실히 통함. 시드 8개로 늘려도 <!-- num:artifacts/cadence_summary_extended.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+7.07<!-- /num -->% |
| ETTh1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.88<!-- /num -->% | 작은 이득. 시드 8개에서는 <!-- num:artifacts/cadence_summary_extended.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.24<!-- /num -->% 로 줄고 시드 둘에 몰림 |
| Weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+0.58<!-- /num -->% | 신뢰구간이 0 을 포함: 효과 없음 |
| Electricity (20) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.15<!-- /num -->% | 신뢰구간이 0 을 포함: 효과 없음 |

- 재학습이 통하는 ETTh2 에서는 오차 감시(Page–Hinkley)가 재학습 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/n_refits:.0f -->19<!-- /num -->회로 매일 재학습 이득의 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.98<!-- /num -->배를 얻습니다.
- **승격 게이트**(후보가 직전 14일의 현역보다 나을 때만 교체)는 이상 구간에서 학습된 나쁜 모델이 서비스에 오르는 것을 막습니다. 이상 구간에서 울리는 비율 규칙은 ETTh1 에서 오히려 해로웠습니다(<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/improvement_vs_never_pct:+.1f -->-2.6<!-- /num -->%).
- 사전 가설 H1~H4 중 둘(H1 재학습은 늘 도움이 된다, H3 웜 스타트는 비용 1/3)은 기각됐고 그대로 적었습니다. 전체 격자·신뢰구간·차트는 [docs/results.md](docs/results.md).

![etth2 재학습 횟수 대 MAE](docs/assets/charts/pareto_etth2.svg)

## 3. 데모

다섯 단계를 한 화면에서 보여 주고, 모든 버튼이 실제 API 를 부릅니다.

| 단계 | 화면에서 하는 일 |
|---|---|
| 1 · [데이터](docs/assets/demo/01-data.png) | 배포된 데이터의 출처(URL·SHA-256)와 검사 결과를 보고, **내 CSV 를 올려** 같은 검사(중복·역행·간격·결측·상수 채널)를 돌립니다 |
| 2 · [모델 비교](docs/assets/demo/02-models.png) | naive → Linear → DLinear → PatchTST 를 같은 분할에서 비교하고, 계열을 골라 **후보를 학습**합니다. 게이트는 후보의 검증 MAE 가 현재 모델보다 낮을 때만 승격합니다 |
| 3 · [배포](docs/assets/demo/03-deploy.png) | 버전 표에서 **한 번 눌러 활성화·롤백**, 모델 카드(학습 구간·지표·해시·입출력 계약), 지금 시점의 예측을 실제값과 겹쳐 보기 |
| 4 · [감시 · 재학습](docs/assets/demo/04-monitor.png) | ETTh1 의 마지막 1년을 시간순으로 재생합니다. 검출기가 울리면 worker 가 재학습하고, API 는 해시·참조 입출력을 **검증한 뒤 포인터만 바꿉니다**. 교체 중 실패하는 요청은 0건(테스트로 고정) |
| 5 · [재학습 정책](docs/assets/demo/05-policy.png) | 이 데이터에 맞는 정책(2절의 오프라인 실험)을 보고, 그 정책으로 재생을 시작합니다 |

위 캡처를 만들 때 실제로 일어난 일([캡처 보고서](docs/assets/demo/capture-report.json)): ① Linear 후보는 게이트가 거부 — "<!-- num:docs/assets/demo/capture-report.json#gate -->게이트 거부: 후보 0.3770 ≥ 현재 0.3722 (val_mae_fixed). 강제로 올릴 수는 있습니다.<!-- /num -->" ② 리플레이 <!-- num:docs/assets/demo/capture-report.json#steps_to_swap:d -->23<!-- /num -->일째 검출기 경보 → worker 재학습 → <!-- num:docs/assets/demo/capture-report.json#first_version -->v0001<!-- /num --> 에서 <!-- num:docs/assets/demo/capture-report.json#monitor/active -->v0003<!-- /num --> 으로 무중단 교체. CI 의 `demo-image` 잡이 같은 흐름(프로필 → CSV 검사 → 후보 학습 → 게이트 → 카드 → 롤백)을 컨테이너에서 매번 실행합니다. API 경로는 [docs/evidence.md](docs/evidence.md#데모의-다섯-단계와-뒤에서-도는-api).

## 4. 시스템 아키텍처

```mermaid
flowchart LR
    A[고정 소스 + 검사] --> B[재학습 캐시: 매일 콜드 학습 1회]
    B --> C[정책 시뮬레이션 · 부트스트랩 · 가설 판정]
    C -. 정책 선택 .-> F
    A -. stream.npz .-> E
    D[레지스트리: ONNX + 해시 + 참조 입출력] --> E[API: /v1/forecast · /v1/observe]
    E --> F[잔차 감시: 같은 검출기 코드]
    F -->|job| G[Worker: 학습 · ONNX · parity]
    G -->|activate| D
    D -->|검증 통과 시 원자적 교체| E
```

| 영역 | 역할 | 구성 요소 |
|---|---|---|
| 데이터 | 고정 소스(URL+SHA-256), 스키마 검사, Polars 리샘플·보간, 시간순 분할 | `src/metronome/data`, `dvc.yaml` |
| 실험 | 재학습 캐시, 정책 20개 시뮬레이션, 7일 블록 부트스트랩, 사전 등록 가설 판정 | `src/metronome/cadence`, `docs/protocol.md` |
| 레지스트리 | ONNX + 해시 + 참조 입출력. 검증에 실패한 모델은 올라가지 않음(fail-closed) | `serving/registry.py`, [ADR 0001](docs/adr/0001-fail-closed-registry.md) |
| 서빙 | ONNX Runtime API(이미지에 torch 없음), 원자적 포인터 교체, Prometheus 지표 | `serving/app.py`, `serving/engine.py` |
| 감시 · 재학습 | 검출기 3종(비율 · Page–Hinkley · ADWIN), worker 의 학습 → ONNX → parity → 등록, 승격 게이트, Airflow DAG | `serving/monitor.py`, `serving/worker.py`, `dags/` |
| 배포 · 운영 | Docker 이미지 3종, compose, Kubernetes, Azure Container Apps(OIDC 자동 배포, Terraform), AWS ECS Express Mode(Fargate, 자동 배포), Render, 6시간 점검 | `.github/workflows`, `deploy/k8s`, `infra/azure` |

**왜 이렇게 했나** — *사전 등록*: 기준을 먼저 커밋해야 기각된 가설(H1·H3)도 그대로 남습니다. *재학습 캐시*: 정책마다 새로 학습하면 비교가 안 되므로 매일 한 번만 학습해 두고 모든 정책이 같은 모델을 씁니다. *ONNX Runtime*: 서빙 이미지에서 torch 를 빼고 PyTorch 출력과의 parity 를 등록 때와 활성화 때 검증합니다. *fail-closed*: 해시나 참조 입출력이 어긋나면 교체를 거부하고 현재 모델을 유지합니다.

## 5. 모델과 검증

- **검증 방식**: 시간순 분할(학습 → 검증 → 시험), 정보 누출 차단(감시는 실제값이 도착해 해결된 오차만 봄), 척도는 초기 학습 구간 표준편차로 고정, 시드 반복과 신뢰구간.
- **계열 비교** (ETTh1, L=336 → H=96, 같은 분할, 표준화 MSE/MAE). 재학습 정책 실험은 **DLinear 로 고정**했습니다. 캐시가 "스트림 일수 × 시드" 번 학습하므로 가벼운 모델이어야 4개 데이터셋을 CPU 로 감당합니다.

| 모델 | 시험 MSE | 시험 MAE | 비고 |
|---|---:|---:|---|
| naive | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/5/mse:.4f -->1.2944<!-- /num --> | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/5/mae:.4f -->0.7132<!-- /num --> | 마지막 값 유지 |
| seasonal naive | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/4/mse:.4f -->0.5122<!-- /num --> | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/4/mae:.4f -->0.4333<!-- /num --> | 하루 전 값 |
| Linear | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/3/mse:.4f -->0.3881<!-- /num --> | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/3/mae:.4f -->0.4113<!-- /num --> | |
| **DLinear (채택)** | **<!-- num:src/metronome/static/evidence.json#leaderboard/etth1/2/mse:.4f -->0.3801<!-- /num -->** | **<!-- num:src/metronome/static/evidence.json#leaderboard/etth1/2/mae:.4f -->0.4018<!-- /num -->** | 학습 <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/2/train_seconds:.0f -->10<!-- /num -->초, 논문 재현 기준 안(ETTh2) |
| NLinear | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/1/mse:.4f -->0.3755<!-- /num --> | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/1/mae:.4f -->0.3962<!-- /num --> | |
| PatchTST | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/0/mse:.4f -->0.3719<!-- /num --> | <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/0/mae:.4f -->0.3970<!-- /num --> | 가장 낮지만 학습 <!-- num:src/metronome/static/evidence.json#leaderboard/etth1/0/train_seconds:.0f -->3278<!-- /num -->초, 논문 재현·추론 벤치에 사용 |

- **승격 게이트(서비스)**: 후보가 서비스에 오르려면 아래를 모두 통과해야 합니다([docs/serving.md](docs/serving.md)).

| 검사 | 기준 | 실패 시 |
|---|---|---|
| 검증 MAE | 후보 < 현역의 최근 7일 MAE(없으면 배포 시 검증 MAE) | 등록만 하고 승격하지 않음(강제 승격은 명시적 옵션) |
| ONNX parity | PyTorch 출력과 최대 절대 차이 ≤ 1e-4 | 등록 거부 |
| 해시 · 참조 입출력 | 활성화 때 다시 계산해 매니페스트와 일치 | 422 로 거부, 현재 모델이 계속 응답 |

- **서빙 성능** (DLinear, 4 vCPU): 모델 호출 p95 가 PyTorch <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/torch/p95_ms:.3f -->0.339<!-- /num --> ms → ONNX Runtime <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/ort_fp32/p95_ms:.3f -->0.118<!-- /num --> ms(배치 1). HTTP 왕복 p50 <!-- num:artifacts/serving/http_latency.json#http_ms/p50:.2f -->4.43<!-- /num --> ms · p95 <!-- num:artifacts/serving/http_latency.json#http_ms/p95:.2f -->5.87<!-- /num --> ms(loopback), 동시 클라이언트 8 에서 <!-- num:artifacts/serving/http_load.json#levels/8/requests_per_s:.0f -->304<!-- /num --> req/s. 자세한 표는 [docs/serving.md](docs/serving.md).
- **테스트 · CI**: pytest 99개(교체 중 요청 손실 0, 검증 실패 시 거부, CSV 검사, 후보 게이트, 롤백, 검출기·캐시·전처리 회귀), 커버리지 하한 70%, Python 3.11–3.13. CI 12개 잡이 lint · 테스트 · 파이프라인 smoke · Docker · compose 와 kind 의 재학습 루프 · Airflow DAG · 데모 이미지 · TensorFlow 교차 재현 · 문서 숫자 대조를 실행합니다.

## 6. 운영

| 항목 | 내용 |
|---|---|
| 배포 | main 에 머지되면 `azure` 워크플로가 이미지를 GHCR 에 게시하고, 키 없는 OIDC 로그인으로 Azure Container Apps(한국 중부, 요청 없으면 0대)를 갱신한 뒤 새 리비전이 건강한지 확인합니다. AWS 는 `aws` 워크플로가 같은 GHCR 이미지로 ECS Express Mode(Fargate, 시드니)를 갱신하고 그 이미지로 안정될 때까지 확인합니다. Render 는 블루프린트로 같은 이미지를 빌드 |
| 인프라 코드 | Azure 리소스 3개를 Terraform 으로 선언, `infra` 워크플로가 실제 리소스를 import 해 `plan` 변경 0건이어야 통과 |
| 컨테이너 | 서빙·worker·데모 이미지, compose, Kubernetes 매니페스트(init Job + api·worker Deployment + 공유 PVC). CI 가 실제 컨테이너와 kind 클러스터에서 감시 → 재학습 → 교체 루프를 끝까지 실행 |
| 감시 · 점검 | `/metrics`(Prometheus), `/v1/monitor`, `cloud-smoke` 가 6시간마다 두 주소의 health · ready · 예측 · 지표 · 리플레이를 점검 |
| 재학습 운영 | worker 가 감시 경보와 주기 요청을 처리. 주 1회 재학습 + 승격 게이트는 Airflow DAG 로 두고 CI 가 `airflow dags test` 로 실행 |
| 롤백 · 장애 | 이전 커밋의 이미지 태그로 재배포, `/v1/models/rollback`, 장애별 대응은 [운영 런북](docs/operations.md) |

## 7. 트러블슈팅

| 문제 | 원인 | 해결 | 교훈 |
|---|---|---|---|
| 이상 구간에서 검출기가 울려 재학습한 모델이 오히려 나빠짐(ETTh1 비율 규칙 <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/improvement_vs_never_pct:+.1f -->-2.6<!-- /num -->%) | 이상 구간 데이터로 학습한 후보를 검증 없이 교체 | 후보가 직전 14일의 현역보다 나을 때만 교체하는 **승격 게이트** 추가. 첫 결과를 본 뒤 넣었으므로 사후 탐색으로 표시 | 재학습 "트리거"와 "승격"은 다른 결정 |
| compose 에서 재학습 요청이 기록되지 않음 | API 컨테이너가 레지스트리를 읽기 전용으로 마운트, 두 이미지의 uid 불일치. 로컬 프로세스로는 재현 안 됨 | CI `compose` 잡이 실제 컨테이너 두 개로 루프를 돌리다 Read-only file system 으로 드러남 → uid 통일, 볼륨 쓰기 가능 | 컨테이너 경계는 실제 컨테이너로 CI 에서 돌려야 보임 |
| H2 통계가 시드별 비율 평균의 폭주로 깨짐 | 이득이 0 근처인 데이터셋에서 비율의 분모가 0 에 가까움 | 시드 평균 MAE 의 비율로 정의를 바꾸고, 이득이 확인된 데이터셋에서만 계산. 판정은 그대로, 변경 이력에 날짜·이유 기록 | 비율 통계는 분모를 먼저 의심 |
| Terraform 원격 상태 저장소 생성이 `SubscriptionNotFound` | 배포용 ID 가 리소스 그룹 범위라 Storage 공급자를 등록할 수 없음 | 원격 상태 대신 매 실행마다 실제 리소스를 import 하고 plan 변경 0건을 검사 | 최소 권한 ID 는 IaC 의 상태 저장 방식까지 정함 |

## 8. 공고 항목 대응

| 공고 | 이 프로젝트에서 |
|---|---|
| AI 모델 설계·학습 | Linear · NLinear · DLinear · PatchTST 직접 구현, 단일 학습 루프(시드·조기 종료·lr 스케줄·웜 스타트) |
| 데이터 전처리 파이프라인 | 고정 소스 · 스키마 검사 · Polars 리샘플·보간 · 학습 구간 전용 스케일러 · DVC · CSV 검사 API |
| 모델 성능 평가·개선 | 재학습 캐시 위 정책 20개, 부트스트랩 구간, 사전 등록 가설, 계열 리더보드와 후보 게이트, Optuna 탐색(H5 기각) |
| 추론 최적화 | ONNX Runtime 서빙, parity 검증, INT8 비교, HTTP 지연과 동시 클라이언트 1·8·32 처리량 |
| 실험 결과 문서화 | 문서의 숫자를 JSON 과 CI 가 대조, 프로토콜 변경 이력, ADR, 사후 탐색 표시 |
| Python · ML 기본 | mypy strict · ruff · pytest(커버리지 하한 70%), 시간순 분할, 정보 누출 차단, 기준 모델, 시드와 신뢰구간 |
| Git 협업 · 소통 | 이슈 → 브랜치 → 템플릿 PR → CI → merge commit, CODEOWNERS · CONTRIBUTING, 결함과 대응을 사후 탐색으로 구분해 기록 |
| PyTorch · TensorFlow | PyTorch 학습 루프, 같은 DLinear 를 Keras 로 교차 재현(가중치 이식 시 출력 일치) |
| MLOps | 검증하는 레지스트리와 원자적 교체, MLflow, DVC, Airflow DAG(주 1회 재학습 + 게이트) |
| 클라우드 운영 | Azure Container Apps 자동 배포(OIDC) + AWS ECS Fargate 자동 배포 + Render, Terraform(plan 0건), Kubernetes(kind), GHCR, 6시간 점검, 런북 |
| 대규모 데이터 | M4 100,000 시계열을 Polars · pandas · PySpark 로 처리해 일치 검사, Spark standalone 클러스터(CI) |
| 논문 재현 | DLinear · PatchTST 보고값 대조, 기준 밖 설정도 시드 편차와 함께 보고 |

항목별 근거 파일과 자세한 설명은 [docs/evidence.md](docs/evidence.md).

## 9. 실행

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[train,export,dev]"
pytest -q                                   # 합성 데이터, 네트워크 불필요

metronome prepare etth1                     # 고정 SHA-256 으로 내려받아 검사·Parquet
metronome deploy-init etth1 --registry registry/etth1   # v0001 학습 → ONNX → 검증 → 활성화
metronome serve --registry registry/etth1   # http://127.0.0.1:8000 (대시보드, /docs)
metronome worker --registry registry/etth1  # 다른 터미널: 재학습 job 처리
```

컨테이너로는 `docker compose run --rm init && docker compose up api worker`. 실험 전체는 `dvc repro`(4 vCPU 기준 수 시간).

## 10. 문서

[프로토콜(사전 등록)](docs/protocol.md) · [결과](docs/results.md) · [공고 항목별 근거](docs/evidence.md) · [서비스·추론 최적화](docs/serving.md) · [운영 런북](docs/operations.md) · [논문 재현](docs/reproduction.md) · [모델 개선 탐색](docs/model_search.md) · [대용량 처리](docs/bigdata.md) · [설계](docs/design.md) · [ADR](docs/adr/0001-fail-closed-registry.md) · [범위와 조건](docs/scope.md)

## 11. 회고

- 가설과 판정 기준을 먼저 커밋해 두니, 기대와 다른 결과(재학습이 안 통하는 데이터셋, 기각된 가설 둘)를 고치지 않고 그대로 적을 수 있었습니다. 결론이 "데이터에 따라 다르다"로 끝나도 그 근거가 남습니다.
- 로컬 프로세스로는 멀쩡하던 재학습 루프가 실제 컨테이너 두 개로 돌리자 깨졌습니다. 그 뒤로 compose · kind · Airflow · 데모 이미지를 전부 CI 가 실제로 실행하게 했습니다.
- 문서의 숫자를 결과 파일에 묶어 CI 가 대조하게 한 것이 가장 효과가 컸습니다. 실험을 다시 돌릴 때마다 문서가 틀리는 일이 사라졌습니다.

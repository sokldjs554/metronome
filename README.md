# Metronome

**배포된 시계열 예측 모델을 언제 다시 학습할지, 데이터로 정합니다.** 재학습 정책(안 함 · 주기적 · 오차 감시)을 같은 데이터·같은 모델·같은 척도로
비교하고, 그 결론대로 움직이는 non-stop 서빙(감시 → 재학습 → 검증 → 무중단 교체)을 붙였습니다. 공개 벤치마크(ETT · Jena weather · UCI electricity · M4) 위의 개인 프로젝트입니다.

**바로 보기** → [Azure 데모](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io) · [Render 데모](https://metronome-demo.onrender.com) · [브라우저 리플레이(서버 없음)](https://sokldjs554.github.io/metronome/) — 서버 데모는 첫 접속에 1분 안팎 걸립니다.

![Metronome 데모 — 데이터 검사, 모델 계열 비교와 게이트, 원클릭 배포, 오차 감시와 무중단 교체, 재학습 정책](docs/assets/demo/demo.gif)

## 데모: 다섯 단계, 모든 버튼이 실제 API

| 단계 | 화면에서 하는 일 |
|---|---|
| 1 · [데이터](docs/assets/demo/01-data.png) | 배포된 데이터의 출처(URL·SHA-256)와 검사 결과를 보고, **내 CSV 를 올려** 같은 검사(중복·역행·간격·결측·상수 채널)를 돌립니다 |
| 2 · [모델 비교](docs/assets/demo/02-models.png) | naive → Linear → DLinear → PatchTST 를 같은 분할에서 비교하고, 계열을 골라 **후보를 학습**합니다. 게이트는 후보의 검증 MAE 가 현재 모델보다 낮을 때만 승격합니다 |
| 3 · [배포](docs/assets/demo/03-deploy.png) | 버전 표에서 **한 번 눌러 활성화·롤백**, 모델 카드(학습 구간·지표·해시·입출력 계약), 지금 시점의 예측을 실제값과 겹쳐 보기 |
| 4 · [감시 · 재학습](docs/assets/demo/04-monitor.png) | ETTh1 의 마지막 1년을 시간순으로 재생합니다. 검출기가 울리면 worker 가 재학습하고, API 는 해시·참조 입출력을 **검증한 뒤 포인터만 바꿉니다**. 교체 중 실패하는 요청은 0건(테스트로 고정) |
| 5 · [재학습 정책](docs/assets/demo/05-policy.png) | 이 데이터에 맞는 정책(아래 오프라인 실험)을 보고, 그 정책으로 재생을 시작합니다 |

CI 의 `demo-image` 잡이 같은 흐름(프로필 → CSV 검사 → 후보 학습 → 게이트 → 카드 → 롤백)을 컨테이너에서 매번 실행합니다. API 경로와 배포 방법은 [docs/evidence.md](docs/evidence.md#데모의-다섯-단계와-뒤에서-도는-api) 와 [운영 런북](docs/operations.md).

## 핵심 결과: 재학습 효과는 데이터마다 다르고, 미리 잴 수 있다

DLinear 를 4개 데이터셋의 마지막 1년 스트림에서 매일 콜드 재학습한 **캐시** 위에 정책 20개를 시뮬레이션했습니다
(시드 3개, 프로토콜은 실행 전에 [고정](docs/protocol.md), 수치는 저장소의 JSON 에서 읽어 CI 가 대조).

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

## 어떻게 동작하나

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

설계 결정은 [docs/design.md](docs/design.md), 레지스트리의 fail-closed 규칙은 [ADR 0001](docs/adr/0001-fail-closed-registry.md).

## 공고 항목 대응

| 공고 | 이 프로젝트에서 |
|---|---|
| AI 모델 설계·학습 | Linear · NLinear · DLinear · PatchTST 를 직접 구현, 단일 학습 루프(시드·조기 종료·lr 스케줄·웜 스타트) |
| 데이터 전처리 파이프라인 | URL+SHA-256 고정 소스, 스키마 검사, Polars 리샘플·보간, 학습 구간 전용 스케일러, DVC, CSV 검사 API |
| 모델 성능 평가·개선 | 재학습 캐시 위 정책 20개, 부트스트랩 구간, 사전 등록 가설, 계열 리더보드와 후보 게이트, Optuna 탐색(H5 기각) |
| 추론 최적화 | ONNX Runtime 서빙(이미지에 torch 없음), parity 검증, INT8 비교, HTTP 지연과 동시 클라이언트 1·8·32 처리량 |
| 실험 결과 문서화 | 문서의 숫자를 JSON 과 CI 가 대조, 프로토콜 변경 이력, ADR, 사후 탐색 표시 |
| Python · ML 기본 | mypy strict · ruff · pytest(커버리지 하한 70%), Python 3.11–3.13 CI, 시간순 분할, 정보 누출 차단, 기준 모델, 시드와 신뢰구간 |
| Git 협업 · 소통 | 이슈 → 브랜치 → 템플릿 PR → CI → merge commit, CODEOWNERS · CONTRIBUTING, 결함과 대응을 사후 탐색으로 구분해 기록 |
| PyTorch · TensorFlow | PyTorch 학습 루프, 같은 DLinear 를 Keras 로 교차 재현(가중치 이식 시 출력 일치) |
| MLOps | 해시·참조 입출력으로 검증하는 레지스트리와 원자적 교체, MLflow, DVC, Airflow DAG(주 1회 재학습 + 게이트, CI 가 끝까지 실행) |
| 클라우드 운영 | Azure Container Apps 자동 배포(OIDC) + Render, Terraform(plan 변경 0건), Kubernetes(kind, CI), GHCR 이미지, 6시간 점검, 런북 |
| 대규모 데이터 | M4 <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->100,000<!-- /num --> 시계열을 Polars · pandas · PySpark 로 처리해 일치 검사, Spark standalone 클러스터(CI) |
| 논문 재현 | DLinear · PatchTST 보고값 대조, 기준 밖 설정도 시드 편차와 함께 보고 |

항목별 근거 파일과 자세한 설명은 [docs/evidence.md](docs/evidence.md).

## 실행

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

## 문서

[프로토콜(사전 등록)](docs/protocol.md) · [결과](docs/results.md) · [공고 항목별 근거](docs/evidence.md) · [모델 개선 탐색](docs/model_search.md) · [논문 재현](docs/reproduction.md) · [서비스·추론 최적화](docs/serving.md) ·
[대용량 처리](docs/bigdata.md) · [운영 런북](docs/operations.md) · [설계](docs/design.md) · [ADR](docs/adr/0001-fail-closed-registry.md) · [범위와 조건](docs/scope.md)

데이터는 공개 벤치마크를 시간순으로 재생한 것이고, 개인 프로젝트로 이슈 → 브랜치 → PR → CI 흐름을 갖춰 진행했습니다. 실험 조건과 범위는 [docs/scope.md](docs/scope.md) 에 있습니다.

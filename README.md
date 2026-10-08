# Metronome

**배포된 시계열 예측 모델을 언제 다시 학습할지, 데이터로 정합니다.** 재학습 정책(안 함 · 주기적 · 오차 감시 기반)을
같은 데이터·같은 모델·같은 척도로 비교하고, 그 결론대로 움직이는 **non-stop 서빙**(감시 → 재학습 → 검증 → 무중단 교체)을 붙였습니다.

> 모든 데이터는 **공개 벤치마크**(ETT, Jena weather, UCI electricity, PeMS traffic, M4)입니다.
> 개인 프로젝트입니다.

## 데모: 다섯 단계를 한 화면에서

![Metronome 데모 — 데이터 검사, 모델 계열 비교와 게이트, 원클릭 배포, 오차 감시와 무중단 교체, 재학습 정책](docs/assets/demo/demo.gif)

대시보드는 Model Craft 류 제품이 묶는 흐름을 그대로 따라갑니다. 모든 버튼은 실제 API 를 부릅니다.

| 단계 | 화면에서 하는 일 | 뒤에서 도는 것 |
|---|---|---|
| 1 · [데이터](docs/assets/demo/01-data.png) | 배포된 데이터의 출처(URL·SHA-256)·분할·채널 통계·검사 결과를 보고, **내 CSV 를 올려** 같은 검사(중복·역행·간격·결측·상수 채널)를 돌려 봅니다 | `GET /v1/data/profile`, `POST /v1/data/validate` → `data.schema.validate_frame` |
| 2 · [모델 비교](docs/assets/demo/02-models.png) | 같은 분할에서 비교한 모델 계열(naive → Linear → DLinear → PatchTST)의 시험 오차·파라미터·학습 시간을 보고, 계열을 골라 **후보를 학습**합니다. 게이트는 후보의 검증 MAE 가 현재 모델보다 낮을 때만 승격합니다 | `GET /v1/leaderboard`, `POST /v1/candidates` → worker 가 학습·ONNX·parity·등록, `POST /v1/candidates/promote` |
| 3 · [배포](docs/assets/demo/03-deploy.png) | 버전 표에서 **한 번 눌러 활성화·롤백**, 모델 카드(학습 구간·지표·해시·입출력 계약) 열기, 지금 시점에서 **예측을 호출**해 실제값과 겹쳐 보기 | `POST /v1/models/{v}/activate`(해시·참조 입출력 재검증), `POST /v1/models/rollback`, `GET /v1/models/{v}/card`, `POST /v1/forecast` |
| 4 · [감시 · 재학습](docs/assets/demo/04-monitor.png) | ETTh1 의 마지막 1년을 시간순으로 재생합니다. 검출기(비율·Page–Hinkley·ADWIN)가 울리면 재학습이 요청되고, worker 가 등록한 새 버전을 API 가 **검증한 뒤 포인터만 바꿉니다**. 교체 중 요청은 하나도 실패하지 않습니다(테스트로 고정) | `POST /v1/replay/*`, `POST /v1/observe`, `GET /v1/monitor`, `GET /metrics` |
| 5 · [재학습 정책](docs/assets/demo/05-policy.png) | 이 데이터셋에서 어떤 재학습 정책이 좋은지(오프라인 실험, 사전 등록) 보고, 그 정책으로 재생을 시작합니다 | `static/evidence.json` ← `artifacts/cadence_summary.json`(숫자는 CI 가 대조) |

[모바일](docs/assets/demo/06-mobile.png) · [캡처 보고서](docs/assets/demo/capture-report.json) · [검사용 예시 CSV](docs/assets/demo/sample.csv). 캡처는 `scripts/capture_demo.py` 가 실제 서비스를 돌려 만들고, CI 의 `demo-image` 잡이 같은 흐름(프로필 → CSV 검사 → 후보 학습 → 게이트 → 카드 → 롤백)을 컨테이너에서 매번 실행합니다.

**서버 데모 → [Azure Container Apps](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io) · [Render](https://metronome-demo.onrender.com)** — 같은 이미지로 실제 서빙 스택(ONNX Runtime API, 감시, 재학습)이 돌고 있습니다. Azure 는 main 에 머지될 때마다 GitHub Actions 가 키 없는 OIDC 로그인으로 자동 배포하고(한국 중부, 요청이 없으면 0대로 축소), Render 는 블루프린트로 올렸습니다. 둘 다 요청이 없으면 잠들어 첫 요청에 1분 안팎 걸립니다. `cloud-smoke` 가 6시간마다 두 주소의 health·ready·예측·지표·리플레이를 점검합니다.

**브라우저에서 직접 돌려보기 → [Metronome Replay](https://sokldjs554.github.io/metronome/)** — 서버 없이 한 파일로 같은 1년 스트림을 재생합니다.
실제 서빙 스택에서 기록한 리플레이(`scripts/record_replay.py`)의 각 버전 DLinear 가중치를 ONNX 에서 꺼내 브라우저가 직접
예측을 계산하고, 같은 검출기(비율·Page–Hinkley·ADWIN)의 JS 포팅이 같은 날에 경보를 냅니다. 페이지는
`scripts/build_demo_page.py` 가 기록 JSON 과 오프라인 증거(`static/evidence.json`)로 조립합니다.

**내 계정에 공개 배포(Render, 무료 플랜)**: 저장소를 포크 → Render 대시보드에서 *New → Blueprint* → 포크한 저장소 선택 →
`render.yaml` 이 `Dockerfile.demo` 를 빌드합니다(ETTh1 다운로드 + v0001 학습, 약 10분). 빌드가 끝나면 `/` 가 대시보드,
`/ready` 가 헬스체크입니다. `METRONOME_API_KEY` 를 비우면 누구나 리플레이를 시작할 수 있는 열린 데모가 됩니다.

```bash
docker compose run --rm init && docker compose up api worker   # http://localhost:8000
```

## 질문: 다시 학습하면 얼마나 좋아지고, 얼마나 자주 해야 하는가

DLinear 를 4개 데이터셋의 마지막 1년(weather 는 180일) 스트림에서 매일 콜드 재학습한 **재학습 캐시** 위에 20개 정책을
시뮬레이션했습니다. 값은 시드 평균(시드 수는 표에 표시), 초기 학습 구간 표준편차 단위의 MAE 입니다. 프로토콜은 실행 전에
[고정](docs/protocol.md)했고, 수치는 저장소의 JSON 에서 마커로 읽어 CI 가 대조합니다.

| 데이터셋 | 시드 | 재학습 안 함 | 매일 재학습 | 개선율 | 95% 구간 (매일 − 안 함) | 주 1회 + 승격 게이트 (교체 횟수) |
|---|---:|---:|---:|---:|---|---|
| ETTh1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/n_seeds:d -->3<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_mean:.4f -->0.4799<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->0.4706<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.88<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0131<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0056<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4690<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->16.0<!-- /num -->) |
| ETTh2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/never/n_seeds:d -->3<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/never/mae_mean:.4f -->0.3401<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->0.3169<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+6.79<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0297<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0168<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.3166<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->18.7<!-- /num -->) |
| Weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/never/n_seeds:d -->3<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/never/mae_mean:.4f -->0.4359<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->0.4332<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+0.58<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0096<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0043<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4330<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->10.7<!-- /num -->) |
| Electricity (20) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/never/n_seeds:d -->3<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/never/mae_mean:.4f -->0.2237<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->0.2240<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.15<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0001<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0008<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.2235<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->15.3<!-- /num -->) |

**답은 "데이터에 따라 다르다"이고, 그걸 미리 알 수 있다는 것이 이 프로젝트의 핵심입니다.** ETTh2 는 매일 재학습으로 MAE 가
<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:.1f -->6.8<!-- /num -->% 내려가지만
weather 와 electricity 는 재학습해도 좋아지지 않습니다(구간이 0 을 포함). 재학습이 통하는 데이터에서는 오차 감시(Page–Hinkley)가
매일 재학습 이득의 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.98<!-- /num -->배를
재학습 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/n_refits:.0f -->19<!-- /num -->회로 얻고,
**승격 게이트**(후보가 직전 14일의 현역보다 나을 때만 교체)는 이상 구간에서 학습된 나쁜 모델이 서비스에 오르는 것을 막아
비율 규칙의 손해를 덜어 내지만, 잘 통하는 ETTh2 에서는 중립이거나 조금 손해입니다. 이상 구간에서 울리는 비율 규칙은 ETTh1 에서 오히려 해로웠습니다
(<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/improvement_vs_never_pct:+.1f -->-2.6<!-- /num -->%).

사전 가설 판정 — H1(재학습은 도움이 된다): <!-- num:artifacts/cadence_summary.json#hypotheses/H1/pass -->False<!-- /num -->,
H2(감시 정책이 적은 재학습으로 이득의 80%): <!-- num:artifacts/cadence_summary.json#hypotheses/H2/pass -->True<!-- /num -->,
H3(웜 스타트 1/3 비용): <!-- num:artifacts/cadence_summary.json#hypotheses/H3/pass -->False<!-- /num -->,
H4(확장 창 ≥ 슬라이딩 창): <!-- num:artifacts/cadence_summary.json#hypotheses/H4/pass -->True<!-- /num -->.
시드를 8개로 늘린 사후 확장도 같은 결론입니다: ETTh2 는 시드 8개 중 <!-- num:artifacts/cadence_summary_extended.json#datasets/etth2/expanding/policies/periodic-1/n_seeds_better_than_never:d -->8<!-- /num -->개에서 매일 재학습이 낫고
(<!-- num:artifacts/cadence_summary_extended.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+7.07<!-- /num -->%), ETTh1 의 작은 이득(<!-- num:artifacts/cadence_summary_extended.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.24<!-- /num -->%)은 시드 둘에 몰려 있으며,
weather 는 <!-- num:artifacts/cadence_summary_extended.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+0.02<!-- /num -->% 로 사실상 0 입니다.
전체 격자·구간·차트는 [docs/results.md](docs/results.md) 에 있습니다.

![etth2 재학습 횟수 대 MAE](docs/assets/charts/pareto_etth2.svg)

## 공고 항목별 구현과 검증 근거

| 공고 | 구현 | 어디서 확인하나 |
|---|---|---|
| AI 모델 설계·학습 | DLinear · NLinear · Linear · PatchTST 를 논문 설명으로 직접 구현, 단일 학습 루프(시드·조기 종료·lr 스케줄·웜 스타트) | `src/metronome/models`, `train/trainer.py`, `tests/test_models.py` |
| 데이터 전처리 파이프라인 | URL+SHA-256 고정 소스, 스키마 검사(결측·중복·역행·간격), Polars 리샘플·보간, 학습 구간 전용 스케일러, DVC 단계 | `src/metronome/data`, `dvc.yaml`, `tests/test_data.py` |
| 모델 성능 평가·개선 | 재학습 캐시 위 20개 정책, 7일 블록 부트스트랩 구간, 사전 등록 가설 H1~H5, 승격 게이트, Optuna 로 검증 구간에서만 고르고 시험은 한 번 보는 모델 개선 탐색(H5 기각: 논문 레시피가 이미 최적 근처) | `src/metronome/cadence`, `src/metronome/tune`, [protocol.md](docs/protocol.md), [results.md](docs/results.md), [model_search.md](docs/model_search.md) |
| 서비스 적용을 위한 추론 최적화 | ONNX Runtime 서빙(이미지에 torch 없음), parity 검증, 동적 INT8 비교, 엔진 교대 지연 벤치, HTTP 지연과 동시 클라이언트 1·8·32 처리량(한 worker 가 어디서 포화하는지) | `src/metronome/export`, `scripts/http_load.py`, [serving.md](docs/serving.md) |
| 실험 결과 문서화·공유 | 숫자 마커(문서 ↔ JSON 대조를 CI 가 수행), 프로토콜 변경 이력, ADR, 사후 탐색 표시 | `scripts/check_numbers.py`, `docs/` |
| Python 기반 개발 | 전 모듈 Python, 타입 힌트와 mypy strict(데이터·검출기·캐시·서빙), ruff, pytest(커버리지 하한 70% 를 CI 가 강제), Python 3.11·3.12·3.13 을 CI 가 실행 | `pyproject.toml`, `tests/`, `.github/workflows/ci.yml` |
| 머신러닝 기본 이론 | 시간순 분할, 정보 누출 차단(해결된 오차만 감시), 고정 척도, 기준 모델(naive·seasonal naive), 시드 반복과 신뢰구간 | `data/splits.py`, `serving/monitor.py`, [reproduction.md](docs/reproduction.md) |
| 데이터 분석·전처리 경험 | 4개 벤치마크 + M4 100,000 시계열 wide→long, 세 엔진 일치 검사 | `src/metronome/bigdata`, [bigdata.md](docs/bigdata.md) |
| Git 기반 협업 | 이슈 → 기능 브랜치 → 템플릿을 채운 PR → CI 통과 → merge commit 머지로 진행했습니다([이슈](https://github.com/sokldjs554/metronome/issues?q=is%3Aissue), [PR](https://github.com/sokldjs554/metronome/pulls?q=is%3Apr+is%3Amerged)). 브랜치 간 충돌은 main 병합으로 풀었고, CODEOWNERS·이슈 템플릿·CONTRIBUTING 으로 규칙을 고정했습니다. CI 는 lint · 테스트 3.11/3.12/3.13 · 파이프라인 smoke · Docker · compose 재학습 루프 · Kubernetes(kind) 재학습 루프 · Airflow DAG 실행 · 데모 이미지(다섯 단계 경로) · TensorFlow · 숫자 대조이고, 운영 워크플로로 Azure 자동 배포, Terraform plan 대조, 두 주소 6시간 점검, GHCR 이미지 게시, GitHub Pages 데모 배포, Spark 클러스터 실행이 있습니다 | `.github/`, [CONTRIBUTING.md](CONTRIBUTING.md) |
| 문제 해결 중심 소통 | 첫 결과에서 본 결함(이상 구간 재학습이 모델을 망침)과 그 대응(게이트)을 사후 탐색으로 구분해 기록 | [protocol.md 변경 이력](docs/protocol.md#변경-이력), [results.md](docs/results.md) |
| PyTorch 또는 TensorFlow (우대) | PyTorch 로 모델과 학습 루프를 구현하고, 같은 DLinear 를 TensorFlow/Keras 로도 구현해 가중치 이식 시 출력 일치, 같은 초기값·배치 순서로 함께 학습 시 시험 MSE 차이 0.001% 미만을 확인했습니다(사전 등록 P15) | `src/metronome/models`, `src/metronome/tfmodels.py`, [reproduction.md](docs/reproduction.md#tensorflow-교차-재현-protocol-p15) |
| MLOps (우대) | 해시·참조 입출력으로 검증하는 파일 레지스트리와 원자적 교체, MLflow(sqlite) 기록, DVC 파이프라인(`dvc dag`: prepare → cache → simulate → report), 승격 게이트. 실험에서 좋았던 주 1회 재학습 + 승격 게이트 정책은 Airflow DAG(`dags/metronome_retrain.py`)로 운영하며, CI 가 데모 API 를 띄우고 `airflow dags test` 로 끝까지 실행합니다 | `serving/registry.py`, `tracking/`, `dvc.yaml`, [ADR 0001](docs/adr/0001-fail-closed-registry.md) |
| 클라우드 환경 운영 (우대) | 브라우저 리플레이를 GitHub Pages 에 자동 배포해 공개로 운영하고(배포 후 공개 주소를 직접 확인), main 머지마다 서빙·worker 이미지를 GHCR 에 커밋 태그로 게시합니다(롤백용). Docker 이미지 3종의 감시 → 재학습 → 교체 루프는 compose(`docker-compose.yml`)와 Kubernetes 매니페스트(`deploy/k8s`, init Job + api·worker Deployment + 공유 PVC) 두 구성으로 있고, CI 의 `compose` 잡과 `k8s` 잡이 각각 실제 컨테이너와 kind 클러스터에서 같은 루프를 끝까지 실행합니다. 서버 데모는 main 에 머지될 때마다 `azure` 워크플로가 키 없는 OIDC 로그인으로 [Azure Container Apps](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io) 에 자동 배포하고(이미지 게시 → 앱 갱신 → 트래픽을 받는 리비전이 그 이미지로 건강한지 확인 → 점검), Render 블루프린트(`render.yaml`)로도 [올렸습니다](https://metronome-demo.onrender.com). Azure 의 리소스 3개(리소스 그룹, Container Apps 환경, 앱)는 Terraform(`infra/azure`)으로 선언하고, `infra` 워크플로가 main 에서 실제 리소스를 import 한 뒤 `terraform plan` 이 **변경 0건이어야 통과**합니다(코드 = 실제 상태). `cloud-smoke` 가 6시간마다 두 주소의 health·ready·배포 계약·예측 5회·Prometheus 지표·리플레이를 점검하고, 배포·롤백(이전 커밋의 이미지 태그로 재배포)·장애 대응은 운영 런북에 적었습니다 | `.github/workflows/azure.yml`·`infra.yml`·`cloud-smoke.yml`·`images.yml`·`pages.yml`, `infra/azure`, `deploy/k8s`, `Dockerfile*`, `docker-compose.yml`, `render.yaml`, [운영 런북](docs/operations.md) |
| 대규모 데이터 처리 (우대) | M4 <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->100,000<!-- /num --> 시계열(<!-- num:artifacts/bigdata/bigdata.json#engines/0/n_cells:, -->24,002,047<!-- /num --> 셀)을 Polars·pandas·PySpark(`local[4]`)로 처리해 결과가 같음을 검사했습니다. 같은 Spark 코드를 standalone 클러스터(master 1 + worker 2, 각자 컨테이너, 공유 볼륨)에 올려 Polars 와 결과가 같고 두 worker 가 태스크를 <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/completed_tasks -->39<!-- /num -->개·<!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/completed_tasks -->52<!-- /num -->개로 나눠 처리함을 확인했으며(protocol P16), CI 가 같은 구성을 다시 실행합니다. 한 호스트 위의 컨테이너 클러스터입니다 | `src/metronome/bigdata`, `docker-compose.spark.yml`, [bigdata.md](docs/bigdata.md#클러스터-실행-protocol-p16) |
| 논문 구현·재현 (우대) | DLinear·PatchTST 를 논문 설명으로 구현해 보고값과 대조했습니다. 기준(MSE ±3%) 안인 설정과 밖인 설정(DLinear·Linear ETTh1)을 시드 편차와 함께 그대로 적었습니다 | `models`, `eval/ltsf.py`, [reproduction.md](docs/reproduction.md) |

공고의 주요업무 5개·자격요건 7개·우대사항 5개 중 경력 무관·학력 무관은 지원 허용 조건이라 표에서 뺐습니다. 나머지 15개를 항목마다 한 줄로 대응했고, 근거 파일을 같은 줄에 적었습니다.

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

설계 결정과 버린 대안은 [docs/design.md](docs/design.md), 레지스트리의 fail-closed 규칙은 [ADR 0001](docs/adr/0001-fail-closed-registry.md) 에 있습니다.

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

실험 전체는 `bash scripts/run_cache_all.sh && bash scripts/run_warm_all.sh && metronome simulate … && metronome report`
(4 vCPU 기준 수 시간), 또는 `dvc repro`. 서빙 이미지만 쓰려면 `pip install .` 로 충분합니다(ONNX Runtime + NumPy).

## 문서

[프로토콜(사전 등록)](docs/protocol.md) · [결과](docs/results.md) · [모델 개선 탐색](docs/model_search.md) · [논문 재현](docs/reproduction.md) · [서비스·추론 최적화](docs/serving.md) ·
[대용량 처리](docs/bigdata.md) · [운영 런북](docs/operations.md) · [설계](docs/design.md) · [ADR](docs/adr/0001-fail-closed-registry.md) · [범위와 조건](docs/scope.md)

## 범위

데이터는 공개 벤치마크(ETTh1·ETTh2·Jena weather·UCI electricity 20채널, M4)를 시간순으로 재생한 것이고, 개인 프로젝트로 이슈 → 브랜치 → PR → CI 흐름을 갖춰 진행했습니다.
Kubernetes 매니페스트는 CI 의 한 노드 kind 클러스터에서, Airflow DAG 는 CI 의 `airflow dags test` 로, Terraform 은 실제 Azure 리소스와의 `plan` 대조로 검증했고,
서버 데모는 Azure Container Apps 와 Render 에 올렸습니다. Spark 클러스터는 서버 한 대 위의 컨테이너 3개(master 1 + worker 2)입니다.
실험 조건과 범위는 [docs/scope.md](docs/scope.md) 에 있습니다. 데이터의 권리는 각 제공자에게 있으며 코드는 MIT 입니다.

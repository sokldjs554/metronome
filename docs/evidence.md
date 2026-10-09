# 공고 항목별 구현과 검증 근거

README 의 요약 표를 항목마다 구현 내용과 근거 파일로 풀어 쓴 것입니다. 수치는 저장소의 JSON 에서 마커로 읽어 CI 가 대조합니다.

| 공고 | 구현 | 어디서 확인하나 |
|---|---|---|
| AI 모델 설계·학습 | DLinear · NLinear · Linear · PatchTST 를 논문 설명으로 직접 구현, 단일 학습 루프(시드·조기 종료·lr 스케줄·웜 스타트) | `src/metronome/models`, `train/trainer.py`, `tests/test_models.py` |
| 데이터 전처리 파이프라인 | URL+SHA-256 고정 소스, 스키마 검사(결측·중복·역행·간격), Polars 리샘플·보간, 학습 구간 전용 스케일러, DVC 단계 | `src/metronome/data`, `dvc.yaml`, `tests/test_data.py` |
| 모델 성능 평가·개선 | 재학습 캐시 위 20개 정책, 7일 블록 부트스트랩 구간, 사전 등록 가설 H1~H5, 승격 게이트, Optuna 로 검증 구간에서만 고르고 시험은 한 번 보는 모델 개선 탐색(H5 기각: 논문 레시피가 이미 최적 근처) | `src/metronome/cadence`, `src/metronome/tune`, [protocol.md](protocol.md), [results.md](results.md), [model_search.md](model_search.md) |
| 서비스 적용을 위한 추론 최적화 | ONNX Runtime 서빙(이미지에 torch 없음), parity 검증, 동적 INT8 비교, 엔진 교대 지연 벤치, HTTP 지연과 동시 클라이언트 1·8·32 처리량(한 worker 가 어디서 포화하는지) | `src/metronome/export`, `scripts/http_load.py`, [serving.md](serving.md) |
| 실험 결과 문서화·공유 | 숫자 마커(문서 ↔ JSON 대조를 CI 가 수행), 프로토콜 변경 이력, ADR, 사후 탐색 표시 | `scripts/check_numbers.py`, `docs/` |
| Python 기반 개발 | 전 모듈 Python, 타입 힌트와 mypy strict(데이터·검출기·캐시·서빙), ruff, pytest(커버리지 하한 70% 를 CI 가 강제), Python 3.11·3.12·3.13 을 CI 가 실행 | `pyproject.toml`, `tests/`, `.github/workflows/ci.yml` |
| 머신러닝 기본 이론 | 시간순 분할, 정보 누출 차단(해결된 오차만 감시), 고정 척도, 기준 모델(naive·seasonal naive), 시드 반복과 신뢰구간 | `data/splits.py`, `serving/monitor.py`, [reproduction.md](reproduction.md) |
| 데이터 분석·전처리 경험 | 4개 벤치마크 + M4 100,000 시계열 wide→long, 세 엔진 일치 검사 | `src/metronome/bigdata`, [bigdata.md](bigdata.md) |
| Git 기반 협업 | 이슈 → 기능 브랜치 → 템플릿을 채운 PR → CI 통과 → merge commit 머지로 진행했습니다([이슈](https://github.com/sokldjs554/metronome/issues?q=is%3Aissue), [PR](https://github.com/sokldjs554/metronome/pulls?q=is%3Apr+is%3Amerged)). 브랜치 간 충돌은 main 병합으로 풀었고, CODEOWNERS·이슈 템플릿·CONTRIBUTING 으로 규칙을 고정했습니다. CI 는 lint · 테스트 3.11/3.12/3.13 · 파이프라인 smoke · Docker · compose 재학습 루프 · Kubernetes(kind) 재학습 루프 · Airflow DAG 실행 · 데모 이미지(다섯 단계 경로) · TensorFlow · 숫자 대조이고, 운영 워크플로로 Azure 자동 배포, Terraform plan 대조, 두 주소 6시간 점검, GHCR 이미지 게시, GitHub Pages 데모 배포, Spark 클러스터 실행이 있습니다 | `.github/`, [CONTRIBUTING.md](../CONTRIBUTING.md) |
| 문제 해결 중심 소통 | 첫 결과에서 본 결함(이상 구간 재학습이 모델을 망침)과 그 대응(게이트)을 사후 탐색으로 구분해 기록 | [protocol.md 변경 이력](protocol.md#변경-이력), [results.md](results.md) |
| PyTorch 또는 TensorFlow (우대) | PyTorch 로 모델과 학습 루프를 구현하고, 같은 DLinear 를 TensorFlow/Keras 로도 구현해 가중치 이식 시 출력 일치, 같은 초기값·배치 순서로 함께 학습 시 시험 MSE 차이 0.001% 미만을 확인했습니다(사전 등록 P15) | `src/metronome/models`, `src/metronome/tfmodels.py`, [reproduction.md](reproduction.md#tensorflow-교차-재현-protocol-p15) |
| MLOps (우대) | 해시·참조 입출력으로 검증하는 파일 레지스트리와 원자적 교체, MLflow(sqlite) 기록, DVC 파이프라인(`dvc dag`: prepare → cache → simulate → report), 승격 게이트. 실험에서 좋았던 주 1회 재학습 + 승격 게이트 정책은 Airflow DAG(`dags/metronome_retrain.py`)로 운영하며, CI 가 데모 API 를 띄우고 `airflow dags test` 로 끝까지 실행합니다 | `serving/registry.py`, `tracking/`, `dvc.yaml`, [ADR 0001](adr/0001-fail-closed-registry.md) |
| 클라우드 환경 운영 (우대) | 브라우저 리플레이를 GitHub Pages 에 자동 배포해 공개로 운영하고(배포 후 공개 주소를 직접 확인), main 머지마다 서빙·worker 이미지를 GHCR 에 커밋 태그로 게시합니다(롤백용). Docker 이미지 3종의 감시 → 재학습 → 교체 루프는 compose(`docker-compose.yml`)와 Kubernetes 매니페스트(`deploy/k8s`, init Job + api·worker Deployment + 공유 PVC) 두 구성으로 있고, CI 의 `compose` 잡과 `k8s` 잡이 각각 실제 컨테이너와 kind 클러스터에서 같은 루프를 끝까지 실행합니다. 서버 데모는 main 에 머지될 때마다 `azure` 워크플로가 키 없는 OIDC 로그인으로 [Azure Container Apps](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io) 에 자동 배포하고(이미지 게시 → 앱 갱신 → 트래픽을 받는 리비전이 그 이미지로 건강한지 확인 → 점검), Render 블루프린트(`render.yaml`)로도 [올렸습니다](https://metronome-demo.onrender.com). AWS 에는 `aws` 워크플로가 같은 GHCR 이미지를 [ECS Express Mode](https://me-f271425dbfde4ebf8bb88ef9e5d409c7.ecs.ap-southeast-2.on.aws)(Fargate 1 vCPU·2 GB, 로드밸런서 뒤 HTTPS, 시드니 리전)에 배포하고 그 이미지로 안정될 때까지 확인한 뒤 점검합니다(초기 설정은 `aws-bootstrap` 워크플로가 역할·클러스터·로그 그룹을 만들고 리전별 허용 여부를 표로 남김). Azure 의 리소스 3개(리소스 그룹, Container Apps 환경, 앱)는 Terraform(`infra/azure`)으로 선언하고, `infra` 워크플로가 main 에서 실제 리소스를 import 한 뒤 `terraform plan` 이 **변경 0건이어야 통과**합니다(코드 = 실제 상태). `cloud-smoke` 가 6시간마다 세 주소의 health·ready·배포 계약·예측 5회·Prometheus 지표·리플레이를 점검하고, 배포·롤백(이전 커밋의 이미지 태그로 재배포)·장애 대응은 운영 런북에 적었습니다 | `.github/workflows/azure.yml`·`aws.yml`·`aws-bootstrap.yml`·`infra.yml`·`cloud-smoke.yml`·`images.yml`·`pages.yml`, `infra/azure`, `deploy/k8s`, `Dockerfile*`, `docker-compose.yml`, `render.yaml`, [운영 런북](operations.md) |
| 대규모 데이터 처리 (우대) | M4 <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->100,000<!-- /num --> 시계열(<!-- num:artifacts/bigdata/bigdata.json#engines/0/n_cells:, -->24,002,047<!-- /num --> 셀)을 Polars·pandas·PySpark(`local[4]`)로 처리해 결과가 같음을 검사했습니다. 같은 Spark 코드를 standalone 클러스터(master 1 + worker 2, 각자 컨테이너, 공유 볼륨)에 올려 Polars 와 결과가 같고 두 worker 가 태스크를 <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/completed_tasks -->39<!-- /num -->개·<!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/completed_tasks -->52<!-- /num -->개로 나눠 처리함을 확인했으며(protocol P16), CI 가 같은 구성을 다시 실행합니다. 한 호스트 위의 컨테이너 클러스터입니다 | `src/metronome/bigdata`, `docker-compose.spark.yml`, [bigdata.md](bigdata.md#클러스터-실행-protocol-p16) |
| 논문 구현·재현 (우대) | DLinear·PatchTST 를 논문 설명으로 구현해 보고값과 대조했습니다. 기준(MSE ±3%) 안인 설정과 밖인 설정(DLinear·Linear ETTh1)을 시드 편차와 함께 그대로 적었습니다 | `models`, `eval/ltsf.py`, [reproduction.md](reproduction.md) |

공고의 주요업무 5개·자격요건 7개·우대사항 5개 중 경력 무관·학력 무관은 지원 허용 조건이라 표에서 뺐습니다. 나머지 15개를 항목마다 한 줄로 대응했고, 근거 파일을 같은 줄에 적었습니다.

## 데모의 다섯 단계와 뒤에서 도는 API

대시보드는 Model Craft 류 제품이 묶는 흐름을 그대로 따라갑니다. 모든 버튼은 실제 API 를 부릅니다.

| 단계 | 화면에서 하는 일 | 뒤에서 도는 것 |
|---|---|---|
| 1 · [데이터](assets/demo/01-data.png) | 배포된 데이터의 출처(URL·SHA-256)·분할·채널 통계·검사 결과를 보고, **내 CSV 를 올려** 같은 검사(중복·역행·간격·결측·상수 채널)를 돌려 봅니다 | `GET /v1/data/profile`, `POST /v1/data/validate` → `data.schema.validate_frame` |
| 2 · [모델 비교](assets/demo/02-models.png) | 같은 분할에서 비교한 모델 계열(naive → Linear → DLinear → PatchTST)의 시험 오차·파라미터·학습 시간을 보고, 계열을 골라 **후보를 학습**합니다. 게이트는 후보의 검증 MAE 가 현재 모델보다 낮을 때만 승격합니다 | `GET /v1/leaderboard`, `POST /v1/candidates` → worker 가 학습·ONNX·parity·등록, `POST /v1/candidates/promote` |
| 3 · [배포](assets/demo/03-deploy.png) | 버전 표에서 **한 번 눌러 활성화·롤백**, 모델 카드(학습 구간·지표·해시·입출력 계약) 열기, 지금 시점에서 **예측을 호출**해 실제값과 겹쳐 보기 | `POST /v1/models/{v}/activate`(해시·참조 입출력 재검증), `POST /v1/models/rollback`, `GET /v1/models/{v}/card`, `POST /v1/forecast` |
| 4 · [감시 · 재학습](assets/demo/04-monitor.png) | ETTh1 의 마지막 1년을 시간순으로 재생합니다. 검출기(비율·Page–Hinkley·ADWIN)가 울리면 재학습이 요청되고, worker 가 등록한 새 버전을 API 가 **검증한 뒤 포인터만 바꿉니다**. 교체 중 요청은 하나도 실패하지 않습니다(테스트로 고정) | `POST /v1/replay/*`, `POST /v1/observe`, `GET /v1/monitor`, `GET /metrics` |
| 5 · [재학습 정책](assets/demo/05-policy.png) | 이 데이터셋에서 어떤 재학습 정책이 좋은지(오프라인 실험, 사전 등록) 보고, 그 정책으로 재생을 시작합니다 | `static/evidence.json` ← `artifacts/cadence_summary.json`(숫자는 CI 가 대조) |

[모바일](assets/demo/06-mobile.png) · [캡처 보고서](assets/demo/capture-report.json) · [검사용 예시 CSV](assets/demo/sample.csv). 캡처는 `scripts/capture_demo.py` 가 실제 서비스를 돌려 만들고, CI 의 `demo-image` 잡이 같은 흐름(프로필 → CSV 검사 → 후보 학습 → 게이트 → 카드 → 롤백)을 컨테이너에서 매번 실행합니다.

**서버 데모 → [Azure Container Apps](https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io) · [AWS ECS](https://me-f271425dbfde4ebf8bb88ef9e5d409c7.ecs.ap-southeast-2.on.aws) · [Render](https://metronome-demo.onrender.com)** — 같은 이미지로 실제 서빙 스택(ONNX Runtime API, 감시, 재학습)이 돌고 있습니다. Azure 는 main 에 머지될 때마다 GitHub Actions 가 키 없는 OIDC 로그인으로 자동 배포하고(한국 중부, 요청이 없으면 0대로 축소), AWS 는 `aws` 워크플로가 같은 이미지로 ECS Express Mode(Fargate, 시드니)를 갱신하고, Render 는 블루프린트로 올렸습니다. Azure 와 Render 는 요청이 없으면 잠들어 첫 요청에 1분 안팎 걸리고, AWS 는 상시 1대라 바로 응답합니다. `cloud-smoke` 가 6시간마다 세 주소의 health·ready·예측·지표·리플레이를 점검합니다.

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

# 서비스: 추론 최적화와 무중단 교체

## API

| 경로 | 역할 |
|---|---|
| `POST /v1/forecast` | `history` (L × C 실수 행렬) → `forecast` (H × C). `origin` 을 주면 지평 타임스탬프를 돌려주고 감시기에 기록 |
| `POST /v1/observe` | 실제값 한 행 도착. 지평이 모두 채워진 예측을 "해결"하고 일별 통계·검출기를 갱신 |
| `GET /v1/monitor` | 기준선(배포 시 검증 MAE), 최근 7일 MAE, 검출기 상태, 경보, 대기 중 재학습 job |
| `GET /v1/models` · `POST /v1/models/{v}/activate` · `POST /v1/models/reload` | 레지스트리 버전 목록, 검증 후 교체(API 키), 디스크 `ACTIVE` 와 동기화 |
| `GET /health` · `GET /ready` | 프로세스 생존 / 검증을 통과한 모델이 메모리에 있을 때만 200 |
| `GET /metrics` | Prometheus: 요청 수(버전별), 지연 히스토그램, 교체 횟수, 최근 7일 MAE, 활성 버전 |
| `POST /v1/replay/start` · `POST /v1/replay/step` · `GET /v1/replay` | 기록된 스트림을 시간순으로 재생(데모·통합 테스트) |
| `GET /v1/data/profile` | 배포된 데이터의 출처(URL·SHA-256), 처리본 해시, 주기·채널·기간, 초기 학습/스트림 분할, 채널별 통계, 구간 평균 스파크라인, 준비 단계의 검사 보고서 |
| `POST /v1/data/validate` | CSV 업로드(multipart, 5 MB 까지) → 같은 파이프라인의 검사(중복·역행·간격·NaN·상수 채널·못 읽은 시각)와 채널 통계, 앞 5행. 파일은 저장하지 않음. polars 가 없는 서빙 이미지에서는 501 |
| `GET /v1/leaderboard` | 오프라인 LTSF 실행에서 모델 계열별 시험 MSE·MAE·파라미터·학습 시간(시드 평균, `static/evidence.json`) + 레지스트리의 실제 버전 목록 |
| `GET /v1/candidates` · `POST /v1/candidates` · `POST /v1/candidates/promote` | 재학습 작업 목록(상태·계열·버전·검증 MAE·게이트 판단). 계열(linear·nlinear·dlinear·patchtst)과 최대 에포크를 골라 후보 학습 작업을 등록(활성화 안 함, 한 번에 하나). 승격은 후보 검증 MAE 가 현재 모델의 최근 7일 MAE(없으면 배포 시 검증 MAE)보다 낮을 때만, `force` 로 수동 활성화 |
| `GET /v1/models/{v}` · `GET /v1/models/{v}/card` · `POST /v1/models/rollback` | 버전 매니페스트, 마크다운 모델 카드(학습 구간·지표·해시·입출력 계약·호출 예), 직전 버전으로 되돌리기(교체 이력 기준, 검증 후 교체) |
| `GET /v1/replay/window` · `GET /v1/workbench` | 현재 스트림 시점의 lookback 입력과 그 뒤 horizon 의 실제값(예측 대 실제 차트용), 대시보드 머리말 요약 |

입력 검증: 행렬 크기, 유한값(NaN·Inf 거부, 422), 채널 수. 검증 오류 응답은 입력을 되돌려주지 않습니다
(NaN 이 섞인 본문이 응답 직렬화를 깨뜨려 500 이 되지 않도록).

## 재학습 → 교체 흐름

```
감시기 경보 또는 주기 도래
  → API 가 registry/jobs/<id>.json 작성 (requested)            ← API 는 학습하지 않는다
  → worker 가 집어감 (training): 스트림[:cutoff] 로 콜드 학습, ONNX 내보내기, parity 검사, 참조 쌍 저장, 등록
  → worker 가 POST /v1/models/<v>/activate
  → API 가 해시 재계산 + 참조 입력 재생(편차 ≤ 1e-4) → 통과 시 포인터 교체, 실패 시 422 + 기존 모델 유지
  → 감시기 기준선을 새 모델의 검증 MAE 로 재설정, 이전 버전이 만든 예측이 해결되는 날은 판정에서 제외
```

교체 중 요청 손실 0 은 `tests/test_serving.py::test_hot_swap_never_drops_a_request` 가 스레드 4개로 교체 4회를 가로지르며
확인합니다. 활성 모델이 학습 중일 때 새 job 을 쌓지 않고(`open_jobs`), 리플레이는 job 이 끝날 때까지 스트림을 멈춥니다
(오프라인 프로토콜의 '다음 날 적용'과 같은 의미).

## 추론 최적화 (protocol P11)

같은 float32 NumPy 입력, 1 intra-op 스레드, 라운드마다 엔진 순서를 교대, 워밍업 <!-- num:artifacts/optimization/benchmark_dlinear.json#warmup -->50<!-- /num -->회 뒤
<!-- num:artifacts/optimization/benchmark_dlinear.json#repeats -->300<!-- /num -->회 측정. 모델 호출 지연이며 HTTP 가 아닙니다.

### DLinear (ETTh1, L=336, H=96, 7채널, 파라미터 <!-- num:artifacts/optimization/benchmark_dlinear.json#n_parameters:, -->64,704<!-- /num -->)

| 배치 | PyTorch eager p95 (ms) | ONNX Runtime FP32 p95 (ms) | ONNX Runtime INT8 p95 (ms) |
|---:|---:|---:|---:|
| 1 | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/torch/p95_ms:.3f -->0.339<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/ort_fp32/p95_ms:.3f -->0.118<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/ort_int8/p95_ms:.3f -->0.084<!-- /num --> |
| 16 | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/16/torch/p95_ms:.3f -->1.496<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/16/ort_fp32/p95_ms:.3f -->0.718<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/16/ort_int8/p95_ms:.3f -->0.576<!-- /num --> |
| 64 | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/64/torch/p95_ms:.3f -->3.826<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/64/ort_fp32/p95_ms:.3f -->2.135<!-- /num --> | <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/64/ort_int8/p95_ms:.3f -->1.738<!-- /num --> |

- ONNX FP32 출력과 PyTorch 의 최대 절대 편차: <!-- num:artifacts/optimization/benchmark_dlinear.json#parity/max_abs_diff:.2e -->4.77e-07<!-- /num --> (허용 1e-4).
  INT8 편차: <!-- num:artifacts/optimization/benchmark_dlinear.json#batches/1/ort_int8/max_abs_diff_vs_torch:.2e -->4.48e-02<!-- /num -->.
- 파일 크기: FP32 <!-- num:artifacts/optimization/benchmark_dlinear.json#sizes_bytes/onnx_fp32:, -->262,242<!-- /num --> B,
  INT8 <!-- num:artifacts/optimization/benchmark_dlinear.json#sizes_bytes/onnx_int8:, -->72,018<!-- /num --> B.
- torch <!-- num:artifacts/optimization/benchmark_dlinear.json#env/torch -->2.14.1+cu130<!-- /num -->,
  onnxruntime <!-- num:artifacts/optimization/benchmark_dlinear.json#env/onnxruntime -->1.30.0<!-- /num -->.

### PatchTST/42 (ETTh1, 파라미터 <!-- num:artifacts/optimization/benchmark_patchtst.json#n_parameters:, -->81,728<!-- /num -->)

| 배치 | PyTorch eager p95 (ms) | ONNX Runtime FP32 p95 (ms) | ONNX Runtime INT8 p95 (ms) |
|---:|---:|---:|---:|
| 1 | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/torch/p95_ms:.3f -->3.092<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/ort_fp32/p95_ms:.3f -->1.631<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/ort_int8/p95_ms:.3f -->1.629<!-- /num --> |
| 16 | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/16/torch/p95_ms:.3f -->19.243<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/16/ort_fp32/p95_ms:.3f -->18.471<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/16/ort_int8/p95_ms:.3f -->19.705<!-- /num --> |
| 64 | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/64/torch/p95_ms:.3f -->81.909<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/64/ort_fp32/p95_ms:.3f -->81.765<!-- /num --> | <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/64/ort_int8/p95_ms:.3f -->79.548<!-- /num --> |

INT8 편차 (배치 1): <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/ort_int8/max_abs_diff_vs_torch:.2e -->1.14e-02<!-- /num -->.

**PatchTST 에서 INT8 은 이득이 없습니다.** 배치 16 에서는 FP32 <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/16/ort_fp32/p95_ms:.3f -->18.471<!-- /num --> ms 대 INT8 <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/16/ort_int8/p95_ms:.3f -->19.705<!-- /num --> ms 로 오히려 느리고, 배치 1 에서도 같은 수준(<!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/ort_fp32/p95_ms:.3f -->1.631<!-- /num --> 대 <!-- num:artifacts/optimization/benchmark_patchtst.json#batches/1/ort_int8/p95_ms:.3f -->1.629<!-- /num --> ms)입니다. 원인은 확인하지 않았습니다. 어텐션·정규화 연산의 비중이 커서 동적 양자화가 줄일 부분이 작을 수 있지만 연산별 프로파일을 하지 않아 가설일 뿐입니다. 이득이 있었던 것은 PyTorch eager 에서 ONNX Runtime FP32 로 옮긴 배치 1 의 한 걸음입니다(위 표).

**채택:** 서빙 엔진은 ONNX Runtime FP32 입니다. INT8 은 수치와 편차를 보고 데이터셋별로 판단할 수 있도록 표만 남깁니다.
서빙 이미지는 PyTorch 를 설치하지 않습니다(`Dockerfile`, CI `docker` 잡이 `import torch` 가 실패하는지 확인).

## HTTP 지연 (protocol P13)

uvicorn 1 worker, loopback, keep-alive, 직렬 <!-- num:artifacts/serving/http_latency.json#n -->500<!-- /num -->회:
p50 <!-- num:artifacts/serving/http_latency.json#http_ms/p50:.2f -->4.43<!-- /num --> ms,
p95 <!-- num:artifacts/serving/http_latency.json#http_ms/p95:.2f -->5.87<!-- /num --> ms
(그중 모델 호출 p50 <!-- num:artifacts/serving/http_latency.json#model_call_ms/p50:.3f -->0.174<!-- /num --> ms).
나머지는 JSON 파싱·검증·직렬화입니다. 운영 SLA 가 아니라 이 머신의 측정값입니다.

### 동시 요청 (P13 확장, 사후)

같은 서버(uvicorn 1 worker)에 클라이언트 N 개가 동시에 배치 1 요청을 보냅니다(`scripts/http_load.py`, 클라이언트당
<!-- num:artifacts/serving/http_load.json#per_client -->200<!-- /num -->회, <!-- num:artifacts/serving/http_load.json#cpu_count -->4<!-- /num --> vCPU):

| 동시 클라이언트 | 처리량 (req/s) | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---:|---:|---:|---:|
| 1 | <!-- num:artifacts/serving/http_load.json#levels/1/requests_per_s:.0f -->188<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/1/http_ms/p50:.1f -->5.3<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/1/http_ms/p95:.1f -->6.4<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/1/http_ms/p99:.1f -->7.8<!-- /num --> |
| 8 | <!-- num:artifacts/serving/http_load.json#levels/8/requests_per_s:.0f -->304<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/8/http_ms/p50:.1f -->24.1<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/8/http_ms/p95:.1f -->47.7<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/8/http_ms/p99:.1f -->60.1<!-- /num --> |
| 32 | <!-- num:artifacts/serving/http_load.json#levels/32/requests_per_s:.0f -->350<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/32/http_ms/p50:.1f -->84.0<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/32/http_ms/p95:.1f -->166.0<!-- /num --> | <!-- num:artifacts/serving/http_load.json#levels/32/http_ms/p99:.1f -->219.9<!-- /num --> |

**한 프로세스는 300 req/s 안팎에서 포화합니다.** 클라이언트를 8 에서 32 로 늘려도 처리량은 <!-- num:artifacts/serving/http_load.json#levels/8/requests_per_s:.0f -->304<!-- /num --> 에서
<!-- num:artifacts/serving/http_load.json#levels/32/requests_per_s:.0f -->350<!-- /num --> req/s 로 조금 오르고 p95 는 <!-- num:artifacts/serving/http_load.json#levels/8/http_ms/p95:.1f -->47.7<!-- /num --> 에서
<!-- num:artifacts/serving/http_load.json#levels/32/http_ms/p95:.1f -->166.0<!-- /num --> ms 로 늘어납니다. 모델 호출은 0.2 ms 수준이라 병목은 요청당 JSON 처리와 단일 worker 의
스레드 전환이며, 더 받으려면 uvicorn worker 수를 늘리거나(공유 레지스트리라 교체 검증은 프로세스마다 다시 일어남) 요청을 배치로 묶어야 합니다. 둘 다 하지 않았습니다.

## 배포 구성

| 파일 | 내용 |
|---|---|
| `Dockerfile` | ONNX Runtime 전용 서빙 이미지(비 root, uid 10001). 재학습 루프가 없는 정적 서빙이면 레지스트리를 읽기 전용으로 마운트해도 되고, 그때 API 는 기동 시 ACTIVE 를 검증만 하고 다시 쓰지 않으며 재학습 요청을 쓸 수 없으면 오류를 기록하고 계속 서빙합니다 |
| `Dockerfile.worker` | PyTorch CPU + 학습·내보내기(비 root, 같은 uid 10001). 같은 볼륨에 버전을 쓰고 API 에 activate 요청 |
| `docker-compose.yml` | `init`(ETTh1 내려받기 + v0001) → `api` + `worker`. 두 컨테이너가 쓰는 볼륨이라 API 에도 쓰기 권한을 줍니다: API 는 새 버전을 검증한 뒤 ACTIVE 포인터를, 재학습 요청 시 jobs/ 를 씁니다 |
| `Dockerfile.demo` + `render.yaml` | 단일 컨테이너 공개 데모(빌드 시 v0001 학습, `metronome demo` 로 API+worker 스레드) |

CI 의 `docker` 잡은 smoke 레지스트리를 읽기 전용으로 마운트해 `/ready`·`/v1/forecast` 를 확인하고, 컨테이너를
재시작한 뒤 같은 버전이 다시 서빙되는지 대조합니다. `compose` 잡은 README 의 두 컨테이너 배포를 끝까지 돌립니다:
init 이 v0001 을 학습하고, 재생이 재학습을 요청하면 worker 컨테이너가 v0002 를 학습·등록하고 API 가 검증 후 교체하는지 확인합니다.
이 잡을 추가하기 전에는 compose 의 API 가 레지스트리를 읽기 전용으로 마운트해 컨테이너에서는 재학습 요청도 모델 교체도 쓸 수 없었습니다.

# 운영 런북

공개로 운영하는 것은 세 가지입니다. 서버 데모는 Render 무료 웹 서비스 하나(`render.yaml`, `Dockerfile.demo`,
https://metronome-demo.onrender.com, 싱가포르 리전, 2026-10-08 배포)이고, 브라우저 리플레이는 GitHub Pages, 서빙·worker 이미지는 GHCR 에 있습니다.
두 컨테이너 구성(`docker-compose.yml`)과 이미지는 같은 코드로 다른 환경에 올릴 때 씁니다.

## 배포

| 무엇 | 어떻게 | 확인 |
|---|---|---|
| 서버 데모 | Render Blueprint 가 `render.yaml` 을 읽어 `Dockerfile.demo` 를 빌드합니다. 빌드 중에 고정 해시의 ETTh1 을 내려받아 v0001 을 학습합니다. main 에 머지되면 Render 가 다시 빌드합니다 | `cloud-smoke` 워크플로 |
| 이미지 | main 에 코드·이미지 변경이 머지되면 `images` 워크플로가 서빙·worker 이미지를 GHCR 에 `sha-<커밋>` 과 `latest` 로 게시합니다 | 워크플로 요약의 이미지 이름 |
| 브라우저 리플레이 | main 의 `docs/demo/metronome-replay.html` 이 바뀌면 `pages` 워크플로가 GitHub Pages(https://sokldjs554.github.io/metronome/)에 배포하고, 공개 주소가 페이지를 내주는지 확인합니다. 서버가 없어 Render 와 무관하게 열립니다 | `pages` 워크플로 요약의 live 주소 |
| 두 컨테이너 | `docker compose run --rm init` 후 `docker compose up api worker`. CI 의 `compose` 잡이 같은 절차를 매번 실행합니다 | `/ready`, `/v1/events` |

배포가 끝나면 `cloud-smoke` 를 수동 실행합니다(Actions → cloud-smoke → Run workflow). 대상은 실행할 때 넣은 주소, 저장소 변수
`RENDER_URL`, 기본값 https://metronome-demo.onrender.com 순서로 정합니다. 서비스를 다른 이름으로 다시 만들면 `RENDER_URL` 만 바꾸면 됩니다.

## 점검과 알림

`cloud-smoke` 는 6시간마다 다음을 확인하고, 지연을 실행 요약에 표로 남깁니다. 실패하면 GitHub 가 저장소 소유자에게 알립니다.

1. `/health` 로 잠든 무료 인스턴스를 깨움(최대 5분 재시도)
2. `/ready` 가 `ready: true` 이고 활성 버전이 있는지
3. `/v1/deployment` 의 계약(룩백, 채널, 지평)대로 만든 입력으로 `/v1/forecast` 5회, 출력 길이 확인
4. `/metrics` 에 Prometheus 지표가 있는지
5. `/replay` 가 브라우저 리플레이를 내주는지

서비스 안에서 보는 지표는 다음과 같습니다.

| 경로·지표 | 뜻 |
|---|---|
| `metronome_forecast_requests_total` | 버전별 예측 요청 수 |
| `metronome_forecast_latency_seconds` | 예측 지연 히스토그램 |
| `metronome_model_swaps_total` | 모델 교체 횟수 |
| `metronome_rolling_7d_mae` | 최근 7일 MAE(고정 척도) |
| `metronome_active_version_info` | 현재 서빙 중인 버전 |
| `/v1/monitor` | 검출기 상태, 경보, 대기 중인 재학습 |
| `/v1/events` | 교체와 재학습 요청 이력 |

## 롤백

**모델 롤백.** 레지스트리의 버전은 지워지지 않으므로 이전 버전을 다시 활성화합니다. API 는 해시와 참조 입출력을 다시 검증한 뒤에만
포인터를 바꾸고, 검증에 실패하면 422 를 돌려주고 기존 모델을 유지합니다.

```bash
curl -s $BASE/v1/models                                   # 버전과 지표 확인
curl -s -X POST $BASE/v1/models/v0001/activate -H "x-api-key: $METRONOME_API_KEY"
curl -s $BASE/ready                                       # model 이 v0001 인지
```

**코드 롤백.** Render 대시보드의 Deploys 에서 이전 배포를 Rollback 합니다. 두 컨테이너 구성은 이미지 태그를 이전 커밋의
`sha-<커밋>` 으로 고정해 다시 올립니다.

## 장애 대응

| 증상 | 먼저 볼 것 | 조치 |
|---|---|---|
| `cloud-smoke` 가 `/health` 에서 실패 | Render 대시보드의 Events·Logs | 빌드 실패면 직전 배포로 Rollback, 무료 시간 소진이면 다음 달까지 대기 |
| `/ready` 가 false | `/v1/models` 의 `load_error` | 레지스트리 검증 실패. 직전 버전 activate |
| 지연 급증 | `/metrics` 의 지연 히스토그램, 동시에 돈 재학습 | 무료 인스턴스는 CPU 하나라 재학습 중에는 예측이 느려질 수 있음 |
| 경보가 계속 울림 | `/v1/monitor` 의 경보 날짜와 기준선 | 이상 구간이면 승격 게이트로 나쁜 후보의 교체를 막음([results.md](results.md)) |

## 이 배포의 한계

- 무료 인스턴스는 15분 동안 요청이 없으면 잠들고, 다음 요청에서 깨어나는 데 1분 안팎이 걸립니다.
- 컨테이너 파일 시스템은 재시작·재배포 때 초기화됩니다. 그래서 운영 중에 재학습한 버전은 사라지고 이미지에 구운 v0001 로 돌아갑니다.
  버전을 남기려면 유료 영구 디스크를 레지스트리 경로(`METRONOME_REGISTRY`)에 붙여야 합니다.
- `METRONOME_API_KEY` 를 비워 두면 누구나 리플레이를 시작하고 모델을 활성화할 수 있습니다. 키를 넣으면 활성화·재적재·리플레이 시작이 보호됩니다.
- AWS·GCP·Azure 에서 운영하지 않았습니다. 이미지와 compose 는 어느 컨테이너 플랫폼에서도 같은 방식으로 돌아갑니다.

# 운영 런북

공개로 운영하는 것은 네 가지입니다. 서버 데모(`Dockerfile.demo`)는 Azure Container Apps(https://metronome-demo.politeground-6dc99748.koreacentral.azurecontainerapps.io,
한국 중부, 2026-10-08 배포, main 머지마다 자동 배포), AWS ECS Express Mode(https://me-f271425dbfde4ebf8bb88ef9e5d409c7.ecs.ap-southeast-2.on.aws, 시드니, 2026-10-09 배포,
main 머지마다 자동 배포), Render 무료 웹 서비스(`render.yaml`, https://metronome-demo.onrender.com, 싱가포르 리전,
2026-10-08 배포) 세 곳에 있고, 브라우저 리플레이는 GitHub Pages, 서빙·worker·데모 이미지는 GHCR 에 있습니다.
두 컨테이너 구성(`docker-compose.yml`)과 이미지는 같은 코드로 다른 환경에 올릴 때 씁니다.

## 배포

| 무엇 | 어떻게 | 확인 |
|---|---|---|
| 서버 데모 | Render Blueprint 가 `render.yaml` 을 읽어 `Dockerfile.demo` 를 빌드합니다. 빌드 중에 고정 해시의 ETTh1 을 내려받아 v0001 을 학습합니다. main 에 머지되면 Render 가 다시 빌드합니다 | `cloud-smoke` 워크플로 |
| 서버 데모 (Azure) | main 에 데모 관련 변경이 머지되면 `azure` 워크플로가 `Dockerfile.demo` 를 GHCR 에 `metronome-demo:sha-<커밋>` 으로 게시하고, 키 없는 OIDC 로그인(저장소 Secret `AZURE_CLIENT_ID`·`AZURE_TENANT_ID`·`AZURE_SUBSCRIPTION_ID`, main 브랜치의 Actions 만 허용)으로 Azure Container Apps(`metronome-rg` / `metronome-env`, 한국 중부)의 `metronome-demo` 앱을 그 이미지로 갱신합니다. 그다음 100% 트래픽을 받는 리비전이 그 이미지로 건강한지 확인하고, 공개 주소에 `cloud-smoke` 와 같은 점검을 돌립니다. 요청이 없으면 0대로 줄어듭니다 | `azure` 워크플로 요약의 주소와 점검 표 |
| 서버 데모 (AWS) | 처음 한 번 `aws-bootstrap` 워크플로를 수동 실행해 시드니 리전(ap-southeast-2, 이 계정의 조직 정책이 허용하는 유일한 리전. 워크플로가 리전별 허용 여부를 표로 남김)에 GitHub OIDC 공급자, 배포 역할(이 저장소 main 만 사용 가능), ECS 실행·인프라 역할, ECS 클러스터, 로그 그룹을 만듭니다(OIDC 공급자와 ECR 은 조직 정책이 허용할 때만). 그 뒤 main 에 데모 관련 변경이 머지되면 `aws` 워크플로가 `Dockerfile.demo` 를 GHCR 에 `sha-<커밋>` 으로 올리고(ECR 은 계정이 허용할 때만 선택), ECS Express Mode 서비스(Fargate 1 vCPU·2 GB, ALB 뒤 HTTPS 주소)를 그 이미지로 갱신해, 배포가 그 이미지로 안정될 때까지 기다린 뒤 공개 주소를 점검합니다. 이전 태그를 주고 수동 실행하면 빌드 없이 롤백, `action=delete` 로 서비스와 로드밸런서를 지웁니다. 배포가 롤백되면 서비스 이벤트·서비스 연결 역할·기본 VPC·CloudTrail 의 거부 호출을 로그에 남기며, 새 서비스의 첫 배포가 역할 전파 지연으로 롤백된 경우는 한 번 더 실행하면 됩니다 | 워크플로 요약의 주소, `/ready` |
| Azure 리소스 (코드) | `infra/azure` 의 Terraform 이 리소스 그룹·Container Apps 환경·앱을 선언합니다. `infra` 워크플로가 PR 에서는 `fmt`·`validate`, main 에서는 OIDC 로그인 후 기존 리소스를 상태에 import 하고 `terraform plan` 을 돌려 **변경 0건이어야 통과**합니다(코드 = 실제 상태). 이미지 태그와 리비전은 `azure` 워크플로가 바꾸므로 Terraform 은 무시합니다. 원격 상태는 두지 않습니다(배포용 ID 가 리소스 그룹 범위라 Storage 공급자를 등록할 수 없고, 리소스 3개는 매 실행 import 로 충분합니다). `apply` 는 수동 실행에서 `apply=true` 를 줄 때만 합니다 | `infra` 워크플로 요약의 plan |
| 이미지 | main 에 코드·이미지 변경이 머지되면 `images` 워크플로가 서빙·worker 이미지를 GHCR 에 `sha-<커밋>` 과 `latest` 로 게시합니다 | 워크플로 요약의 이미지 이름 |
| 브라우저 리플레이 | main 의 `docs/demo/metronome-replay.html` 이 바뀌면 `pages` 워크플로가 GitHub Pages(https://sokldjs554.github.io/metronome/)에 배포하고, 공개 주소가 페이지를 내주는지 확인합니다. 서버가 없어 Render 와 무관하게 열립니다 | `pages` 워크플로 요약의 live 주소 |
| 두 컨테이너 | `docker compose run --rm init` 후 `docker compose up api worker`. CI 의 `compose` 잡이 같은 절차를 매번 실행합니다 | `/ready`, `/v1/events` |
| Kubernetes | `kubectl apply -k deploy/k8s/base`(이미지는 GHCR). `deploy-init` Job 이 v0001 을 PVC 에 학습하고, `api`·`worker` Deployment 가 같은 PVC 를 공유합니다. CI 의 `k8s` 잡이 kind 클러스터에서 같은 절차와 재학습 → 교체 루프를 실행합니다. 여러 노드에 올리면 PVC 를 ReadWriteMany 클래스로 바꾸거나 두 Deployment 를 한 노드에 고정해야 합니다 | `kubectl -n metronome get pods`, `/ready` |

배포가 끝나면 `cloud-smoke` 를 수동 실행합니다(Actions → cloud-smoke → Run workflow). 대상은 실행할 때 넣은 주소 하나, 아니면 저장소 변수
`RENDER_URL`·`AZURE_URL`·`AWS_URL`(비어 있으면 워크플로에 적힌 기본 주소) 세 곳입니다. 서비스를 다른 이름으로 다시 만들면 해당 변수만 바꾸면 됩니다.

## 주기 재학습 (Airflow)

실험에서 ETTh1 은 주 1회 재학습에 승격 게이트를 붙인 정책이 교체를 줄이면서 MAE 를 낮췄습니다([results.md](results.md)).
같은 정책이 `dags/metronome_retrain.py` 의 DAG `metronome_weekly_retrain`(매주 월요일 03:00)입니다.

| 태스크 | 하는 일 |
|---|---|
| `champion_state` | `/ready`·`/v1/monitor`·`/v1/replay` 로 현역 버전, 최근 7일 MAE, 재생 중이면 커서를 읽음 |
| `train_candidate` | 레지스트리에 재학습 job 을 쓰고 worker 코드를 활성화 없이 한 번 실행(`activate=False`). 후보는 ONNX 로 내보내고 parity 검사와 등록까지만 |
| `gate` | 후보의 검증 MAE(고정 척도)가 현역의 최근 7일 MAE(없으면 배포 시 검증 MAE)보다 낮을 때만 `activate` 로 분기. 판단은 `METRONOME_GATE_LOG` 에 JSON 으로 남김 |
| `activate` / `keep` | API 에 활성화를 요청(API 가 해시·참조 입출력을 다시 검증) / 현역 유지 |

설정은 Airflow Variable 또는 환경 변수 `METRONOME_API_URL`, `METRONOME_REGISTRY`, `METRONOME_API_KEY`, `METRONOME_MAX_EPOCHS` 입니다.
worker 코드가 PyTorch 를 쓰므로 Airflow 는 `metronome[train,export]` 가 설치된 환경에서 돌립니다. CI 의 `airflow` 잡이 데모 API 를 띄우고
`airflow dags test` 로 DAG 를 끝까지 실행해, 게이트 판단과 그 결과(`/ready` 의 모델)가 맞는지 확인합니다. 검출기 경보에 의한 재학습(서빙 루프)과는
독립이며, 둘 다 같은 레지스트리의 job 파일과 같은 활성화 API 를 씁니다.

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

**코드 롤백.** Render 는 대시보드의 Deploys 에서 이전 배포를 Rollback 합니다. Azure 는 Actions → azure → Run workflow 에 이전 커밋의
`sha-<커밋>` 태그를 넣어 실행하면 빌드 없이 그 이미지로 새 리비전을 만들어 전환합니다. AWS 는 Actions → aws → Run workflow 에 같은 태그를
넣으면 빌드 없이 그 이미지로 서비스를 갱신합니다. 두 컨테이너 구성은 이미지 태그를 이전 커밋의
`sha-<커밋>` 으로 고정해 다시 올립니다.

## 장애 대응

| 증상 | 먼저 볼 것 | 조치 |
|---|---|---|
| `cloud-smoke` 가 `/health` 에서 실패 | Render 대시보드의 Events·Logs | 빌드 실패면 직전 배포로 Rollback, 무료 시간 소진이면 다음 달까지 대기 |
| `cloud-smoke` 가 Azure 주소의 `/health` 에서 실패 | `azure` 워크플로의 마지막 실행, `az containerapp logs show -g metronome-rg -n metronome-demo --tail 200` | 리비전이 Healthy 가 아니면 이전 커밋의 `sha-` 태그로 `azure` 워크플로 재실행, 이미지 pull 실패면 GHCR 패키지가 Public 인지 확인 |
| `cloud-smoke` 가 AWS 주소의 `/health` 에서 실패 | `aws` 워크플로의 마지막 실행(롤백이면 서비스 이벤트와 거부 호출이 로그에 있음), `aws logs tail /ecs/metronome-demo --since 1h --region ap-southeast-2` | 롤백이면 워크플로 재실행, 그래도 실패면 이전 커밋의 `sha-` 태그로 `aws` 워크플로 재실행, 이미지 pull 실패면 GHCR 패키지가 Public 인지 확인 |
| `/ready` 가 false | `/v1/models` 의 `load_error` | 레지스트리 검증 실패. 직전 버전 activate |
| 지연 급증 | `/metrics` 의 지연 히스토그램, 동시에 돈 재학습 | 무료 인스턴스는 CPU 하나라 재학습 중에는 예측이 느려질 수 있음 |
| 경보가 계속 울림 | `/v1/monitor` 의 경보 날짜와 기준선 | 이상 구간이면 승격 게이트로 나쁜 후보의 교체를 막음([results.md](results.md)) |

## 이 배포의 운영 조건

- Render 무료 인스턴스는 15분 동안 요청이 없으면 잠들고, Azure 앱은 요청이 없으면 0대로 줄어듭니다. 둘 다 다음 요청에서 깨어나는 데 1분 안팎이 걸립니다.
- AWS 의 ECS 서비스는 상시 1 태스크(Fargate 1 vCPU·2 GB)라 바로 응답하는 대신 요청이 없어도 Fargate·로드밸런서 비용이 매시간 발생합니다. 데모가 필요 없어지면 Actions → aws → Run workflow 에서 `action=delete` 로 서비스와 로드밸런서를 지우고, AWS Budgets 의 예산 알림을 켜 둡니다.
- Azure 는 Container Apps 소비 플랜의 월 무료 할당량(vCPU·메모리 시간, 요청 수) 안에서 돌리며, 0대 축소 덕에 점검 요청만으로는 할당량을 넘지 않습니다. 구독은 소유자의 무료 계정이라 크레딧·기간이 끝나면 서비스가 멈출 수 있습니다.
- 컨테이너 파일 시스템은 재시작·재배포 때 초기화됩니다. 그래서 운영 중에 재학습한 버전은 사라지고 이미지에 구운 v0001 로 돌아갑니다.
  버전을 남기려면 유료 영구 디스크를 레지스트리 경로(`METRONOME_REGISTRY`)에 붙여야 합니다.
- `METRONOME_API_KEY` 를 비워 두면 누구나 리플레이를 시작하고 모델을 활성화할 수 있습니다. 키를 넣으면 활성화·재적재·리플레이 시작이 보호됩니다.
- 같은 이미지가 compose, kind(Kubernetes), Azure Container Apps, AWS ECS(Fargate), Render 에서 같은 방식으로 돌아갑니다.

# Metronome

**배포된 시계열 예측 모델을 언제 다시 학습할지, 데이터로 정합니다.** 재학습 정책(안 함 · 주기적 · 오차 감시 기반)을
같은 데이터·같은 모델·같은 척도로 비교하고, 그 결론대로 움직이는 **non-stop 서빙**(감시 → 재학습 → 검증 → 무중단 교체)을 붙였습니다.

> 모든 데이터는 **공개 벤치마크**(ETT, Jena weather, UCI electricity, PeMS traffic, M4)입니다. 실제 고객·설비 데이터는 없습니다.
> 개인 프로젝트이며 특정 회사 제품과 연동하지 않았습니다.

## 30초 데모

![Metronome 데모 — 스트림 재생 중 검출기 경보 → 재학습 → 검증된 새 버전으로 무중단 교체](docs/assets/demo/demo.gif)

ETTh1 의 마지막 1년을 시간순으로 재생합니다. 2017-07-02 에 Page–Hinkley 검출기가 울리고, worker 가 그 시점까지의 데이터로
다시 학습한 모델을 ONNX 로 내보내 등록하면, API 가 **해시와 참조 입출력을 다시 검증한 뒤** 포인터만 바꿉니다. 교체 중 요청은
하나도 실패하지 않습니다(테스트로 고정). [첫 화면](docs/assets/demo/01-ready.png) · [교체 직후](docs/assets/demo/05-after-swap.png) ·
[모바일](docs/assets/demo/06-mobile.png) · [캡처 보고서](docs/assets/demo/capture-report.json)

**브라우저에서 직접 돌려보기 → [Metronome Replay](https://claude.ai/artifact/WeQtpXKZxByXb2Vd1eyUTU)** — 서버 없이 한 파일로 같은 1년 스트림을 재생합니다.
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
시뮬레이션했습니다. 값은 시드 3개 평균, 초기 학습 구간 표준편차 단위의 MAE 입니다. 프로토콜은 실행 전에
[고정](docs/protocol.md)했고, 수치는 저장소의 JSON 에서 마커로 읽어 CI 가 대조합니다.

| 데이터셋 | 재학습 안 함 | 매일 재학습 | 개선율 | 95% 구간 (매일 − 안 함) | 주 1회 + 승격 게이트 (교체 횟수) |
|---|---:|---:|---:|---|---|
| ETTh1 | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_mean:.4f -->0.4799<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/mae_mean:.4f -->0.4706<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+1.88<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0131<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0056<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4690<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->16.0<!-- /num -->) |
| ETTh2 | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/never/mae_mean:.4f -->0.3401<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/mae_mean:.4f -->0.3169<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+6.79<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0297<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->-0.0168<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.3166<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->18.7<!-- /num -->) |
| Weather | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/never/mae_mean:.4f -->0.4359<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/mae_mean:.4f -->0.4332<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->+0.58<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0096<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0043<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.4330<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/weather/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->10.7<!-- /num -->) |
| Electricity (20) | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/never/mae_mean:.4f -->0.2237<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/mae_mean:.4f -->0.2240<!-- /num --> | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/improvement_vs_never_pct:+.2f -->-0.14<!-- /num -->% | [<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/lo_mean:+.4f -->-0.0001<!-- /num -->, <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-1/ci_vs_never/hi_mean:+.4f -->+0.0008<!-- /num -->] | <!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/mae_mean:.4f -->0.2235<!-- /num --> (<!-- num:artifacts/cadence_summary.json#datasets/electricity20/expanding/policies/periodic-7+gate/n_refits_mean:.1f -->15.0<!-- /num -->) |

**답은 "데이터에 따라 다르다"이고, 그걸 미리 알 수 있다는 것이 이 프로젝트의 핵심입니다.** ETTh2 는 매일 재학습으로 MAE 가
<!-- num:artifacts/cadence_summary.json#datasets/etth2/expanding/policies/periodic-1/improvement_vs_never_pct:.1f -->6.8<!-- /num -->% 내려가지만
weather 와 electricity 는 재학습해도 좋아지지 않습니다(구간이 0 을 포함). 재학습이 통하는 데이터에서는 오차 감시(Page–Hinkley)가
매일 재학습 이득의 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/gain_fraction:.2f -->0.96<!-- /num -->배를
재학습 <!-- num:artifacts/cadence_summary.json#hypotheses/H2/rows/etth2/n_refits:.0f -->19<!-- /num -->회로 얻고,
**승격 게이트**(후보가 직전 14일의 현역보다 나을 때만 교체)는 이상 구간에서 학습된 나쁜 모델이 서비스에 오르는 것을 막아
재학습이 해로운 데이터에서도 손실을 줄입니다. 이상 구간에서 울리는 비율 규칙은 ETTh1 에서 오히려 해로웠습니다
(<!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/ratio-0.2/improvement_vs_never_pct:+.1f -->-2.6<!-- /num -->%).

사전 가설 판정 — H1(재학습은 도움이 된다): <!-- num:artifacts/cadence_summary.json#hypotheses/H1/pass -->False<!-- /num -->,
H2(감시 정책이 적은 재학습으로 이득의 80%): <!-- num:artifacts/cadence_summary.json#hypotheses/H2/pass -->True<!-- /num -->,
H3(웜 스타트 1/3 비용): <!-- num:artifacts/cadence_summary.json#hypotheses/H3/pass -->False<!-- /num -->,
H4(확장 창 ≥ 슬라이딩 창): <!-- num:artifacts/cadence_summary.json#hypotheses/H4/pass -->True<!-- /num -->.
전체 격자·구간·차트는 [docs/results.md](docs/results.md) 에 있습니다.

![etth2 재학습 횟수 대 MAE](docs/assets/charts/pareto_etth2.svg)

## 공고 항목별 구현과 검증 근거

| 공고 | 구현 | 어디서 확인하나 |
|---|---|---|
| AI 모델 설계·학습 | DLinear · NLinear · Linear · PatchTST 를 논문 설명으로 직접 구현, 단일 학습 루프(시드·조기 종료·lr 스케줄·웜 스타트) | `src/metronome/models`, `train/trainer.py`, `tests/test_models.py` |
| 데이터 전처리 파이프라인 | URL+SHA-256 고정 소스, 스키마 검사(결측·중복·역행·간격), Polars 리샘플·보간, 학습 구간 전용 스케일러, DVC 단계 | `src/metronome/data`, `dvc.yaml`, `tests/test_data.py` |
| 모델 성능 평가·개선 | 재학습 캐시 위 20개 정책, 7일 블록 부트스트랩 구간, 사전 등록 가설 H1~H4, 승격 게이트 | `src/metronome/cadence`, [protocol.md](docs/protocol.md), [results.md](docs/results.md) |
| 서비스 적용을 위한 추론 최적화 | ONNX Runtime 서빙(이미지에 torch 없음), parity 검증, 동적 INT8 비교, 엔진 교대 지연 벤치, HTTP 지연 | `src/metronome/export`, [serving.md](docs/serving.md) |
| 실험 결과 문서화·공유 | 숫자 마커(문서 ↔ JSON 대조를 CI 가 수행), 프로토콜 변경 이력, ADR, 사후 탐색 표시 | `scripts/check_numbers.py`, `docs/` |
| Python · ML 기본 이론 | 시간순 분할, 정보 누출 차단(해결된 오차만 감시), 고정 척도, 기준 모델(naive·seasonal naive) | `data/splits.py`, `serving/monitor.py`, [reproduction.md](docs/reproduction.md) |
| 데이터 분석·전처리 경험 | 4개 벤치마크 + M4 100,000 시계열 wide→long, 세 엔진 일치 검사 | `src/metronome/bigdata`, [bigdata.md](docs/bigdata.md) |
| Git 기반 협업 | 변경별 커밋에 측정과 이유, PR·실험 이슈 템플릿, CONTRIBUTING, CI 5개 잡 | `.github/`, [CONTRIBUTING.md](CONTRIBUTING.md) |
| 문제 해결 중심 소통 | 첫 결과에서 본 결함(이상 구간 재학습이 모델을 망침)과 그 대응(게이트)을 사후 탐색으로 구분해 기록 | [protocol.md 변경 이력](docs/protocol.md#변경-이력), [results.md](docs/results.md) |
| PyTorch · MLOps · 클라우드 · 대규모 · 논문 | PyTorch 학습 / MLflow(sqlite) 미러 + 파일 레지스트리 + DVC / Docker 3종 + compose + Render 블루프린트 / PySpark·Polars / DLinear·PatchTST 논문 대조 | [serving.md](docs/serving.md), [bigdata.md](docs/bigdata.md), [reproduction.md](docs/reproduction.md) |

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

[프로토콜(사전 등록)](docs/protocol.md) · [결과](docs/results.md) · [논문 재현](docs/reproduction.md) · [서비스·추론 최적화](docs/serving.md) ·
[대용량 처리](docs/bigdata.md) · [설계](docs/design.md) · [ADR](docs/adr/0001-fail-closed-registry.md) · [한계](docs/limitations.md)

## 주장하지 않는 것

실제 고객·설비 데이터, 금액으로 환산한 재학습 비용, 다중 노드 클러스터, 모델 구조 탐색, 다인 협업 이력, 운영 SLA.
자세한 조건은 [docs/limitations.md](docs/limitations.md) 에 있습니다. 데이터의 권리는 각 제공자에게 있으며 코드는 MIT 입니다.

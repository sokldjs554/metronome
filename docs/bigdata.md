# 대용량 데이터 처리 (protocol P12)

같은 일을 세 엔진으로 하고, 결과가 같은지 검사한 뒤 시간을 비교합니다. 일은 평범합니다 — 그것이 데이터 파이프라인이
실제로 시간을 쓰는 곳이기 때문입니다.

## 작업

M4 경진대회 학습 데이터 6개 파일(시간·일·주·월·분기·연, 한 행이 한 시계열, 길이가 달라 뒤쪽이 비어 있는 와이드 CSV,
합계 <!-- num:artifacts/bigdata/bigdata.json#source/bytes:, -->257,927,050<!-- /num --> B)을

1. 와이드 → 롱(`series_id, step, value, frequency`)으로 녹이고
2. 빈 셀을 버리고 값을 float64 로 캐스팅한 뒤
3. 주기별로 분할한 zstd Parquet 로 쓰고
4. 다시 읽어 시계열별 길이·평균을 집계합니다.

세 엔진의 **셀 수·시계열 수·평균 합**이 1e-6 상대 오차 안에서 같지 않으면 단계가 실패합니다.

## 결과

| 엔진 | 중앙값 (s, <!-- num:artifacts/bigdata/bigdata.json#repeats -->3<!-- /num -->회) | 셀 수 | 시계열 수 | Parquet 크기 (B) |
|---|---:|---:|---:|---:|
| <!-- num:artifacts/bigdata/bigdata.json#engines/0/engine -->polars<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/median_seconds:.1f -->7.5<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_cells:, -->24,002,047<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->100,000<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/parquet_bytes:, -->89,563,391<!-- /num --> |
| <!-- num:artifacts/bigdata/bigdata.json#engines/1/engine -->pandas<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/median_seconds:.1f -->137.5<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/n_cells:, -->24,002,047<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/n_series:, -->100,000<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/parquet_bytes:, -->127,039,861<!-- /num --> |
| <!-- num:artifacts/bigdata/bigdata.json#engines/2/engine -->spark<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/median_seconds:.1f -->1232.2<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/n_cells:, -->24,002,047<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/n_series:, -->100,000<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/parquet_bytes:, -->95,406,161<!-- /num --> |

세 엔진 일치: <!-- num:artifacts/bigdata/bigdata.json#agree -->True<!-- /num -->.
CPU <!-- num:artifacts/bigdata/bigdata.json#cpu_count -->4<!-- /num -->개,
polars <!-- num:artifacts/bigdata/bigdata.json#versions/polars -->1.44.2<!-- /num -->,
pandas <!-- num:artifacts/bigdata/bigdata.json#versions/pandas -->3.0.6<!-- /num -->,
pyspark <!-- num:artifacts/bigdata/bigdata.json#versions/pyspark -->4.2.0<!-- /num --> (`local[4]`, driver 4g).

## 읽는 법

- Polars 는 `scan_csv → unpivot → sink_parquet` 스트리밍 경로라 와이드 프레임을 메모리에 다 올리지 않습니다.
- pandas 는 파일 하나를 통째로 녹이므로 가장 큰 파일(Monthly, 48,000 × 2,794)에서 메모리 피크가 큽니다.
- PySpark 는 한 머신(`local[4]`, vCPU 4개)에서 Polars 보다 두 자릿수 느립니다. 와이드 CSV 를 문자열로 읽어
  행마다 최대 2,794개 열을 `stack` 으로 펼치는 작업은 Spark 의 행 단위 실행 모델에 가장 불리한 형태이고, JVM 기동과
  셔플 비용이 고정으로 들어갑니다. 이 비교는 "같은 일, 같은 머신" 조건이지 Spark 에 최적화한 파이프라인이 아니며,
  같은 코드가 클러스터로 그대로 확장된다는 점이 Spark 를 쓰는 이유이고, 실제로 클러스터에 올린 결과는
  [아래](#클러스터-실행-protocol-p16)에 있습니다.
- 시간은 같은 머신에서 순차 실행한 중앙값입니다. 실행 조건(동시에 돌던 작업 포함)은
  `artifacts/bigdata/bigdata.json` 의 `notes` 에 적혀 있습니다.

## 클러스터 실행 (protocol P16)

같은 변환 코드(`spark_melt`)를 Spark standalone 클러스터에서 돌립니다. master 1, worker 2(각 2 core·3 GB), driver 1(client mode)이
각각 별도 컨테이너이고(`docker-compose.spark.yml`), 입력 CSV 와 출력 Parquet 은 네 컨테이너가 `/data` 로 마운트한 공유 볼륨에
둡니다(HDFS·객체 저장소 대용). 바뀌는 것은 master URL 과 입력 분할 크기뿐입니다. Spark 기본값(128 MiB)이면 Daily(96 MB)와
Monthly(92 MB)가 각각 태스크 하나가 되어 그 파일을 처리하는 동안 코어 하나만 일하므로, 8 MiB 로 나눴습니다.

```bash
docker compose -f docker-compose.spark.yml up --build --abort-on-container-exit --exit-code-from driver
```

판정: <!-- num:artifacts/bigdata/bigdata_cluster.json#passed -->True<!-- /num --> (Polars 와 일치 <!-- num:artifacts/bigdata/bigdata_cluster.json#agree -->True<!-- /num -->, 두 worker 모두 완료 태스크의 25% 이상 처리 <!-- num:artifacts/bigdata/bigdata_cluster.json#distributed -->True<!-- /num -->).
셀 <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/n_cells:, -->24,002,047<!-- /num -->개, 시계열 <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/n_series:, -->100,000<!-- /num -->개로 Polars 와 같고, 실행 시간은 <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/seconds:.0f -->585<!-- /num --> s(1회)입니다.

| executor | worker | core | 완료 태스크 | 비율 |
|---|---|---:|---:|---:|
| <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/id -->0<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/host -->spark-worker-2<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/cores -->2<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/0/completed_tasks -->39<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#task_share_by_host/spark-worker-2:.0% -->43%<!-- /num --> |
| <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/id -->1<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/host -->spark-worker-1<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/cores -->2<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#executors/1/completed_tasks -->52<!-- /num --> | <!-- num:artifacts/bigdata/bigdata_cluster.json#task_share_by_host/spark-worker-1:.0% -->57%<!-- /num --> |

입력 분할 수는 Daily <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/per_file/1/input_partitions -->12<!-- /num -->개, Monthly <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/per_file/3/input_partitions -->11<!-- /num -->개,
Quarterly <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/per_file/4/input_partitions -->5<!-- /num -->개, Yearly <!-- num:artifacts/bigdata/bigdata_cluster.json#cluster/per_file/5/input_partitions -->4<!-- /num -->개이고,
Hourly·Weekly 는 8 MiB 보다 작아 1개입니다. 완료 태스크가 분할 수 합보다 많은 것은 헤더 추론·Parquet 재읽기·집계 단계의 태스크가 함께 세어지기 때문입니다.

- 판정 기준은 결과 일치와 분산 두 가지이고, 실행 전에 [이슈 #12](https://github.com/sokldjs554/metronome/issues/12) 와
  [protocol P16](protocol.md#p16-spark-클러스터-실행-사후-추가-결과를-보기-전에-고정) 에 고정했습니다. CI 의 `spark-cluster` 워크플로가
  Spark 경로가 바뀔 때마다 같은 compose 를 다시 실행하고, 기준을 못 넘으면 실패합니다.
- 시간은 참고입니다. 네 컨테이너가 vCPU 4개인 호스트 하나를 나눠 썼으므로 다중 노드의 속도를 뜻하지 않습니다.
  같은 driver 컨테이너에서 같은 8 MiB 분할로 돌린 `local[4]` 는 <!-- num:artifacts/bigdata/bigdata_cluster.json#local_same_splits/seconds:.0f -->1579<!-- /num --> s 로 같은 코어 수의 클러스터보다
  느렸지만, 1회 측정이고 원인을 가려 보지 않아 주장하지 않습니다. 위 표의 Spark
  <!-- num:artifacts/bigdata/bigdata.json#engines/2/median_seconds:.1f -->1232.2<!-- /num --> s 와도 실행 환경(호스트 venv, 기본 분할)이 달라 직접 비교하지 않습니다.
- 한 호스트 위의 컨테이너 클러스터입니다. 실제 다중 노드에서 달라지는 것(네트워크 너머의 공유 저장소, 노드 장애와 태스크 재시도,
  데이터 지역성)은 다루지 않았습니다.

재현: `metronome bigdata --repeats 3` (M4 는 고정 SHA-256 으로 내려받습니다).
클러스터: 위 compose 명령(보고서는 driver 의 `/data/out/bigdata_cluster.json`).

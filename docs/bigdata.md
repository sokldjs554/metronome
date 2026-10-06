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
  같은 코드가 클러스터로 그대로 확장된다는 점이 Spark 를 쓰는 이유입니다. 이 저장소는 **클러스터 운영을 주장하지 않습니다.**
- 시간은 같은 머신에서 순차 실행한 중앙값입니다. 실행 조건(동시에 돌던 작업 포함)은
  `artifacts/bigdata/bigdata.json` 의 `notes` 에 적혀 있습니다.

재현: `metronome bigdata --repeats 3` (M4 는 고정 SHA-256 으로 내려받습니다).

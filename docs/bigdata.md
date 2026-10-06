# 대용량 데이터 처리 (protocol P12)

같은 일을 세 엔진으로 하고, 결과가 같은지 검사한 뒤 시간을 비교합니다. 일은 평범합니다 — 그것이 데이터 파이프라인이
실제로 시간을 쓰는 곳이기 때문입니다.

## 작업

M4 경진대회 학습 데이터 6개 파일(시간·일·주·월·분기·연, 한 행이 한 시계열, 길이가 달라 뒤쪽이 비어 있는 와이드 CSV,
합계 <!-- num:artifacts/bigdata/bigdata.json#source/bytes:, -->…<!-- /num --> B)을

1. 와이드 → 롱(`series_id, step, value, frequency`)으로 녹이고
2. 빈 셀을 버리고 값을 float64 로 캐스팅한 뒤
3. 주기별로 분할한 zstd Parquet 로 쓰고
4. 다시 읽어 시계열별 길이·평균을 집계합니다.

세 엔진의 **셀 수·시계열 수·평균 합**이 1e-6 상대 오차 안에서 같지 않으면 단계가 실패합니다.

## 결과

| 엔진 | 중앙값 (s, <!-- num:artifacts/bigdata/bigdata.json#repeats -->…<!-- /num -->회) | 셀 수 | 시계열 수 | Parquet 크기 (B) |
|---|---:|---:|---:|---:|
| <!-- num:artifacts/bigdata/bigdata.json#engines/0/engine -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/median_seconds:.1f -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_cells:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/n_series:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/0/parquet_bytes:, -->…<!-- /num --> |
| <!-- num:artifacts/bigdata/bigdata.json#engines/1/engine -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/median_seconds:.1f -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/n_cells:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/n_series:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/1/parquet_bytes:, -->…<!-- /num --> |
| <!-- num:artifacts/bigdata/bigdata.json#engines/2/engine -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/median_seconds:.1f -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/n_cells:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/n_series:, -->…<!-- /num --> | <!-- num:artifacts/bigdata/bigdata.json#engines/2/parquet_bytes:, -->…<!-- /num --> |

세 엔진 일치: <!-- num:artifacts/bigdata/bigdata.json#agree -->…<!-- /num -->.
CPU <!-- num:artifacts/bigdata/bigdata.json#cpu_count -->…<!-- /num -->개,
polars <!-- num:artifacts/bigdata/bigdata.json#versions/polars -->…<!-- /num -->,
pandas <!-- num:artifacts/bigdata/bigdata.json#versions/pandas -->…<!-- /num -->,
pyspark <!-- num:artifacts/bigdata/bigdata.json#versions/pyspark -->…<!-- /num --> (`local[4]`, driver 4g).

## 읽는 법

- Polars 는 `scan_csv → unpivot → sink_parquet` 스트리밍 경로라 와이드 프레임을 메모리에 다 올리지 않습니다.
- pandas 는 파일 하나를 통째로 녹이므로 가장 큰 파일(Monthly, 48,000 × 2,794)에서 메모리 피크가 큽니다.
- PySpark 는 JVM 기동·셔플 비용이 고정으로 들어 한 머신에서는 느리지만, 같은 코드가 클러스터로 그대로 확장됩니다.
  이 저장소는 **클러스터 운영을 주장하지 않습니다.**
- 시간은 같은 머신에서 순차 실행한 중앙값이며, 실행 중 다른 작업(재학습 캐시)이 함께 돌고 있었다면
  `artifacts/bigdata/bigdata.json` 의 `notes` 에 적습니다.

재현: `metronome bigdata --repeats 3` (M4 는 고정 SHA-256 으로 내려받습니다).

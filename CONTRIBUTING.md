# 기여 안내

개인 포트폴리오 프로젝트이지만, 다른 사람이 변경 이유와 실행 결과를 따라갈 수 있도록 다음을 지킵니다.

## 흐름

1. 이슈(실험 제안 템플릿)에 가설과 **사전 판정 기준**을 적습니다.
2. 브랜치 `exp/<이름>` 또는 `fix/<이름>` 에서 작업합니다.
3. 테스트를 먼저 추가하고(RED), 구현으로 통과시킵니다(GREEN).
4. 실험 수치는 코드가 만든 JSON(`artifacts/`)에서만 가져오고, 문서의 숫자는
   `<!-- num:artifacts/...json#path -->값<!-- /num -->` 마커로 감쌉니다. `scripts/check_numbers.py` 가 CI 에서 대조합니다.
5. PR 템플릿의 항목을 채우고, 프로토콜을 바꿨다면 `docs/protocol.md` 변경 이력에 남깁니다.

## 로컬 검사

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[train,export,dev]"
ruff check src tests scripts && ruff format --check src tests scripts
mypy src/metronome/data src/metronome/drift src/metronome/cadence src/metronome/serving
pytest -q
```

## 커밋 메시지

`type(scope): 요약` 형식(feat, fix, exp, docs, chore). 본문에는 **무엇을 측정했고 수치가 어디에 있는지**를 적습니다.
실패한 실험도 커밋합니다 — 기각된 가설이 가장 유용한 기록일 때가 많습니다.

## 하지 않는 것

- 결과를 본 뒤 판정 기준을 바꾸는 것
- 테스트를 끄거나 건너뛰어 초록으로 만드는 것
- 문서에 손으로 적은 수치

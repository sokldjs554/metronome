# 기여 안내

개인 포트폴리오 프로젝트이지만, 다른 사람이 변경 이유와 실행 결과를 따라갈 수 있도록 다음을 지킵니다.

## 흐름

1. 이슈를 엽니다. 실험이면 실험 제안 템플릿에 가설과 **사전 판정 기준**을, 그 밖에는 기능·작업 또는 버그 템플릿을 씁니다.
2. 브랜치 `feat/`, `fix/`, `exp/`, `docs/`, `chore/` 접두어로 main 에서 갈라 작업합니다. main 에 직접 커밋하지 않습니다.
3. 테스트를 먼저 추가하고(RED), 구현으로 통과시킵니다(GREEN).
4. 실험이면 판정 기준을 `docs/protocol.md` 에 먼저 커밋한 뒤 실행합니다. 커밋 순서가 사전 등록의 증거입니다.
5. 실험 수치는 코드가 만든 JSON(`artifacts/`)에서만 가져오고, 문서의 숫자는
   `<!-- num:artifacts/...json#path -->값<!-- /num -->` 마커로 감쌉니다. `scripts/check_numbers.py` 가 CI 에서 대조합니다.
6. PR 템플릿을 채우고 본문에 `Closes #이슈번호` 를 적습니다. CI 의 모든 잡이 통과해야 머지합니다.
7. 머지는 merge commit 으로 해서 PR 단위 이력을 남깁니다. 다른 PR 이 먼저 들어가 충돌하면 main 을 브랜치에 병합해 풉니다.
8. `CODEOWNERS` 가 프로토콜·서빙·워크플로 변경의 검토자를 지정합니다.

이 흐름은 2026-10-08 부터 적용했습니다. 그 전의 커밋은 main 에 직접 올렸고, 이후 변경은 모두 이슈와 PR 로 진행했습니다.

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

## 무엇을 바꿨나

<!-- 한 문단. 사용자/운영자 관점에서 달라지는 것. -->

## 왜

<!-- 문제 또는 실험 가설. 관련 이슈/프로토콜 항목(P번호) 링크. -->

## 어떻게 확인했나

- [ ] `pytest -q` 통과 (로컬)
- [ ] 수치를 바꿨다면 `python scripts/check_numbers.py --require-markers README.md docs/*.md` 통과
- [ ] 프로토콜(docs/protocol.md)을 바꿨다면 변경 이력에 날짜·이유를 적음
- [ ] 결과 문서(docs/results.md)는 `metronome report` 로 다시 생성함

## 범위 밖

<!-- 이 PR 이 주장하지 않는 것. -->
